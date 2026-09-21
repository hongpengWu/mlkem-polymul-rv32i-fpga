`timescale 1ns / 1ps

module tb_mlkem_polymul_rv32i_profile;
  reg clk = 0;
  reg resetn = 0;
  wire trap, trace_valid, accel_interrupt;
  wire [35:0] trace_data;
  wire [31:0] status;
  always #5 clk = ~clk;

  integer a [0:255];
  integer b [0:255];
  integer expected [0:255];
  reg signed [63:0] accum [0:255];
  reg signed [63:0] product;
  integer i, j, k, trial, errors, timeout_cycles;
  integer first_metrics [0:13];

  mlkem_polymul_rv32i_profile_top dut (
      .clk(clk), .resetn(resetn), .trap(trap),
      .trace_valid(trace_valid), .trace_data(trace_data),
      .accel_interrupt(accel_interrupt), .status_out(status)
  );

  task check_trial;
    begin
      if (trap) begin
        $display("MLKEM PROFILE FAIL trial=%0d: CPU trap, status=%08x", trial, status);
        $finish;
      end
      if (timeout_cycles == 300000) begin
        $display("MLKEM PROFILE FAIL trial=%0d: timeout, status=%08x", trial, status);
        $finish;
      end
      if (status != 32'h600d600d) begin
        $display("MLKEM PROFILE FAIL trial=%0d: status=%08x detail=%08x",
                 trial, status, dut.debug_regs[1]);
        $finish;
      end

      errors = 0;
      for (i = 0; i < 256; i = i + 1) begin
        if (dut.accel.mem_o[i] !== expected[i][15:0]) begin
          errors = errors + 1;
          if (errors <= 8)
            $display("MLKEM PROFILE mismatch i=%0d actual=%0d expected=%0d",
                     i, dut.accel.mem_o[i], expected[i]);
        end
      end
      if (errors != 0) begin
        $display("MLKEM PROFILE FAIL trial=%0d: independent mismatches=%0d", trial, errors);
        $finish;
      end

      if (dut.debug_regs[13] != dut.debug_regs[10]) begin
        $display("MLKEM PROFILE FAIL trial=%0d: stage_sum=%0d self_test=%0d",
                 trial, dut.debug_regs[13], dut.debug_regs[10]);
        $finish;
      end
      if (dut.debug_regs[9] != dut.debug_regs[4] + dut.debug_regs[5] +
                                  dut.debug_regs[6] + dut.debug_regs[7]) begin
        $display("MLKEM PROFILE FAIL trial=%0d: call accounting mismatch", trial);
        $finish;
      end

      if (trial == 1) begin
        for (i = 2; i <= 13; i = i + 1)
          first_metrics[i] = dut.debug_regs[i];
      end else begin
        for (i = 2; i <= 13; i = i + 1)
          if (dut.debug_regs[i] != first_metrics[i]) begin
            $display("MLKEM PROFILE FAIL trial=%0d: metric[%0d]=%0d first=%0d",
                     trial, i, dut.debug_regs[i], first_metrics[i]);
            $finish;
          end
      end

      $display("MLKEM PROFILE PASS trial=%0d: rdcycle=%0d generate=%0d write=%0d start=%0d poll=%0d read=%0d check=%0d call=%0d self_test=%0d core=%0d polls=%0d stage_sum=%0d sim=%0d",
               trial, dut.debug_regs[2], dut.debug_regs[3], dut.debug_regs[4],
               dut.debug_regs[5], dut.debug_regs[6], dut.debug_regs[7],
               dut.debug_regs[8], dut.debug_regs[9], dut.debug_regs[10],
               dut.debug_regs[11], dut.debug_regs[12], dut.debug_regs[13],
               timeout_cycles);
    end
  endtask

  initial begin
    for (i = 0; i < 256; i = i + 1) begin
      a[i] = (17*i*i + 31*i + 7) % 3329;
      b[i] = (29*i*i + 11*i + 19) % 3329;
      accum[i] = 0;
    end
    for (i = 0; i < 256; i = i + 1)
      for (j = 0; j < 256; j = j + 1) begin
        product = a[i] * b[j];
        k = i + j;
        if (k < 256) accum[k] = accum[k] + product;
        else accum[k-256] = accum[k-256] - product;
      end
    for (i = 0; i < 256; i = i + 1) begin
      expected[i] = accum[i] % 3329;
      if (expected[i] < 0) expected[i] = expected[i] + 3329;
    end

    for (trial = 1; trial <= 3; trial = trial + 1) begin
      resetn = 0;
      repeat (10) @(posedge clk);
      resetn <= 1;

      timeout_cycles = 0;
      while ((status != 32'h600d600d) && (status[31:16] != 16'hdead) &&
             (timeout_cycles < 300000)) begin
        @(posedge clk);
        timeout_cycles = timeout_cycles + 1;
      end
      check_trial();
      repeat (5) @(posedge clk);
    end

    $display("MLKEM PROFILE REPEATABILITY PASS: 3/3 runs identical");
    $finish;
  end
endmodule
