`timescale 1ns/1ps

// Exercise the BIST data path at 100 MHz and, concurrently, the complete board
// top driven by its 125 MHz source clock, including MMCM, reset, and LEDs.
module tb_mlkem512_basemul_k2_board #(
    parameter BIST_MEM_FILE = "basemul_bist.mem"
);
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg resetn = 1'b0;
    wire bist_pass, bist_fail, bist_active;
    mlkem512_basemul_k2_bist #(
        .BIST_MEM_FILE(BIST_MEM_FILE), .TIMEOUT_CYCLES(20000)
    ) dut (
        .clk(clk), .resetn(resetn),
        .bist_pass(bist_pass), .bist_fail(bist_fail), .bist_active(bist_active)
    );

    reg sys_clk = 1'b0;
    always #4 sys_clk = ~sys_clk;
    reg btn0 = 1'b1;
    wire [3:0] board_led;
    reg board_tests_complete = 1'b0;
    mlkem512_basemul_k2_pynqz2_top #(.BIST_MEM_FILE(BIST_MEM_FILE)) board_dut (
        .sys_clk(sys_clk), .btn0(btn0), .led(board_led)
    );

    task automatic await_board_pass(input integer run_index);
        integer cycles;
        begin
            cycles = 0;
            while (board_led[0] !== 1'b1 && board_led[1] !== 1'b1 && cycles < 20000) begin
                @(negedge sys_clk);
                cycles = cycles + 1;
            end
            if (board_led !== 4'b0001)
                $fatal(1, "BOARD_TOP_LED_FAIL run=%0d led=%b cycles=%0d locked=%b",
                       run_index, board_led, cycles, board_dut.locked);
            if (board_dut.bist_i.load_transactions !== 32'd640 ||
                board_dut.bist_i.store_transactions !== 32'd128)
                $fatal(1, "BOARD_TOP_COUNT_FAIL run=%0d", run_index);
            repeat (20) @(negedge sys_clk);
            if (board_led !== 4'b0001)
                $fatal(1, "BOARD_TOP_LED_NOT_STICKY run=%0d led=%b", run_index, board_led);
            $display("BOARD_TOP_CASE_PASS run=%0d led=%b core_cycles=%0d",
                     run_index, board_led, board_dut.bist_i.core_cycles);
        end
    endtask

    initial begin : test_board_top
        realtime first_clock_edge;
        repeat (20) @(negedge sys_clk);
        btn0 = 1'b0;
        await_board_pass(0);
        @(posedge board_dut.clk100);
        first_clock_edge = $realtime;
        @(posedge board_dut.clk100);
        if ($realtime - first_clock_edge < 9.99 || $realtime - first_clock_edge > 10.01)
            $fatal(1, "BOARD_TOP_MMCM_PERIOD_FAIL period_ns=%0.3f", $realtime - first_clock_edge);

        // Exercise the actual asynchronous button reset and synchronized
        // release, then require the board LEDs to report a second clean pass.
        @(negedge sys_clk);
        btn0 = 1'b1;
        repeat (20) @(negedge sys_clk);
        if (board_led !== 4'b0000 || board_dut.reset_sync !== 4'b0000)
            $fatal(1, "BOARD_TOP_BUTTON_RESET_FAIL led=%b reset_sync=%b",
                   board_led, board_dut.reset_sync);
        btn0 = 1'b0;
        await_board_pass(1);
        board_tests_complete = 1'b1;
    end

    task automatic reset_bist;
        begin
            @(negedge clk);
            resetn = 1'b0;
            repeat (5) @(negedge clk);
            resetn = 1'b1;
        end
    endtask

    task automatic await_pass(input integer run_index);
        integer cycles;
        begin
            cycles = 0;
            while (!bist_pass && !bist_fail && cycles < 20010) begin
                @(negedge clk);
                cycles = cycles + 1;
            end
            if (bist_pass !== 1'b1 || bist_fail !== 1'b0 || bist_active !== 1'b0)
                $fatal(1, "BOARD_BIST_FAIL run=%0d state=%0d cycles=%0d pass=%b fail=%b",
                       run_index, dut.state, cycles, bist_pass, bist_fail);
            if (dut.load_transactions !== 32'd640 || dut.store_transactions !== 32'd128)
                $fatal(1, "BOARD_BIST_COUNT_FAIL loads=%0d stores=%0d",
                       dut.load_transactions, dut.store_transactions);
            if (dut.accel_busy !== 1'b0 || dut.accel_done !== 1'b1 || dut.accel_error !== 1'b0)
                $fatal(1, "BOARD_BIST_STATUS_FAIL");
            repeat (20) @(negedge clk);
            if (bist_pass !== 1'b1 || bist_fail !== 1'b0 || dut.bus_valid !== 1'b0)
                $fatal(1, "BOARD_BIST_PASS_NOT_STICKY");
            $display("BOARD_BIST_CASE_PASS run=%0d cycles=%0d core_cycles=%0d loads=%0d stores=%0d",
                     run_index, cycles, dut.core_cycles,
                     dut.load_transactions, dut.store_transactions);
        end
    endtask

    initial begin : test_main
        integer cycles;
        $display("BOARD_BIST_TB_START rom=%s", BIST_MEM_FILE);
        reset_bist();
        await_pass(0);
        reset_bist();
        await_pass(1);

        // Corrupt one result response, proving the pass LED depends on data.
        reset_bist();
        cycles = 0;
        while (!(dut.bus_valid && !dut.bus_write && dut.bus_addr == 32'h5000_1a00)
               && cycles < 20000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (cycles == 20000) $fatal(1, "BOARD_BIST_INJECTION_TIMEOUT");
        // The next rising edge accepts the first result read. Hold a mismatch
        // until the controller has consumed that response.
        @(negedge clk);
        force dut.bus_rdata = 32'hdead_beef;
        cycles = 0;
        while (!bist_fail && cycles < 20) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        release dut.bus_rdata;
        if (bist_fail !== 1'b1 || bist_pass !== 1'b0 || bist_active !== 1'b0)
            $fatal(1, "BOARD_BIST_MISMATCH_NOT_DETECTED");
        repeat (20) @(negedge clk);
        if (bist_fail !== 1'b1 || dut.bus_valid !== 1'b0)
            $fatal(1, "BOARD_BIST_FAILURE_NOT_STICKY");
        cycles = 0;
        while (!board_tests_complete && cycles < 50000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (!board_tests_complete) $fatal(1, "BOARD_TOP_COMPLETION_TIMEOUT");
        $display("MLKEM512_BASEMUL_BOARD_BIST_RTL_PASS runs=2 checked_words=256 mismatch_detected=1 board_top_runs=2");
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "BOARD_BIST_GLOBAL_TIMEOUT");
    end
endmodule
