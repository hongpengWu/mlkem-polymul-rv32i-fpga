`timescale 1ns/1ps

// Standalone official K4 subset. The FPGA contains all firmware/input/expected
// data; the CPU checks every output byte. BTN0 restarts the complete self-test.
module mlkem1024_keccak_pynqz2_top #(
    parameter FIRMWARE_INIT_FILE = "board.mem"
) (
    input wire sys_clk,
    input wire btn0,
    output wire [3:0] led
);
    wire clk100_raw, clk100, feedback_raw, feedback, locked;
    MMCME2_BASE #(
        .CLKIN1_PERIOD(8.000), .CLKFBOUT_MULT_F(8.000),
        .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.000),
        .STARTUP_WAIT("FALSE")
    ) clock_manager (
        .CLKIN1(sys_clk), .CLKFBIN(feedback), .RST(1'b0), .PWRDWN(1'b0),
        .CLKFBOUT(feedback_raw), .CLKOUT0(clk100_raw), .LOCKED(locked),
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(),
        .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6()
    );
    BUFG feedback_buffer(.I(feedback_raw), .O(feedback));
    BUFG system_clock_buffer(.I(clk100_raw), .O(clk100));

    // Only these four asynchronous-clear pins receive the asynchronous request.
    // The separate synchronous register prevents an asynchronous-clear Q from
    // driving BRAM controls. System reset asserts at the next clock edge and
    // releases on the fifth stable edge. All Q-to-D/reset fanout remains timed.
    wire reset_request = btn0 || !locked;
    (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) reg [3:0] reset_sync = 0;
    always @(posedge clk100 or posedge reset_request)
        if (reset_request) reset_sync <= 0;
        else reset_sync <= {reset_sync[2:0], 1'b1};
    (* SHREG_EXTRACT = "NO" *) reg resetn = 0;
    always @(posedge clk100) resetn <= reset_sync[3];

    wire trap;
    wire [31:0] status;
    wire [383:0] profile_words;
    mlkem1024_keccak_system #(
        .FIRMWARE_INIT_FILE(FIRMWARE_INIT_FILE), .RAM_ADDR_BITS(15),
        .CPU_ENABLE_MUL(1), .CPU_ENABLE_FAST_MUL(1), .CPU_ENABLE_DIV(1)
    ) system_i (
        .clk(clk100), .resetn(resetn), .trap(trap),
        .status_out(status), .profile_words(profile_words)
    );

    wire passed = status == 32'h4b415450;
    wire failed = status == 32'h4b415446 || trap;
    assign led[0] = resetn && passed && !failed;
    assign led[1] = resetn && failed;
    assign led[2] = resetn && !passed && !failed;
    assign led[3] = !locked || trap;
endmodule
