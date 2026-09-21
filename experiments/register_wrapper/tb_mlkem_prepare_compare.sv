`timescale 1ns / 1ps

module tb_mlkem_prepare_compare #(
    parameter integer INPUT_DIRECT = 0,
    parameter FIRMWARE_FILE = "prepare_buffered.mem"
);
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
  integer i, j, k, errors, timeout_cycles;

  mlkem_polymul_rv32i_profile_top #(
      .FIRMWARE_INIT_FILE(FIRMWARE_FILE)
  ) dut (
      .clk(clk), .resetn(resetn), .trap(trap),
      .trace_valid(trace_valid), .trace_data(trace_data),
      .accel_interrupt(accel_interrupt), .status_out(status)
  );

  mlkem_axi_profile_observer observer (
      .clk(clk), .resetn(resetn),
      .awvalid(dut.c_awvalid), .awready(dut.c_awready), .awaddr(dut.c_awaddr),
      .wvalid(dut.c_wvalid), .wready(dut.c_wready), .wstrb(dut.c_wstrb),
      .bvalid(dut.c_bvalid), .bready(dut.c_bready),
      .arvalid(dut.c_arvalid), .arready(dut.c_arready),
      .araddr(dut.c_araddr), .arprot(dut.c_arprot),
      .rvalid(dut.c_rvalid), .rready(dut.c_rready)
  );

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

    resetn = 0;
    repeat (10) @(posedge clk);
    resetn <= 1;

    timeout_cycles = 0;
    while ((status != 32'h600d600d) && (status[31:16] != 16'hdead) &&
           (timeout_cycles < 300000)) begin
      @(posedge clk);
      timeout_cycles = timeout_cycles + 1;
    end
    @(negedge clk);

    if (trap) $fatal(1, "MLKEM PREPARE FAIL: CPU trap");
    if (timeout_cycles == 300000) $fatal(1, "MLKEM PREPARE FAIL: timeout");
    if (status != 32'h600d600d)
      $fatal(1, "MLKEM PREPARE FAIL: status=%08x detail=%08x",
             status, dut.debug_regs[1]);
    if (dut.debug_regs[2] != INPUT_DIRECT)
      $fatal(1, "MLKEM PREPARE FAIL: firmware mode=%0d expected=%0d",
             dut.debug_regs[2], INPUT_DIRECT);

    errors = 0;
    for (i = 0; i < 256; i = i + 1) begin
      if (dut.accel.mem_o[i] !== expected[i][15:0]) begin
        errors = errors + 1;
        if (errors <= 8)
          $display("MLKEM PREPARE mismatch i=%0d actual=%0d expected=%0d",
                   i, dut.accel.mem_o[i], expected[i]);
      end
    end
    if (errors != 0)
      $fatal(1, "MLKEM PREPARE FAIL: independent mismatches=%0d", errors);

    if (dut.debug_regs[12] != dut.debug_regs[9])
      $fatal(1, "MLKEM PREPARE FAIL: stage_sum=%0d self_test=%0d",
             dut.debug_regs[12], dut.debug_regs[9]);
    if (dut.debug_regs[8] != dut.debug_regs[3] + dut.debug_regs[4] +
                                  dut.debug_regs[5] + dut.debug_regs[6])
      $fatal(1, "MLKEM PREPARE FAIL: end_to_end accounting mismatch");
    if (dut.debug_regs[10] != 4789)
      $fatal(1, "MLKEM PREPARE FAIL: core=%0d expected=4789", dut.debug_regs[10]);

    observer.check_call(dut.debug_regs[11]);
    $display("AXI_MODE mode=%s", INPUT_DIRECT ? "direct" : "buffered");
    observer.report(INPUT_DIRECT + 1);
    $display("MLKEM PREPARE PASS mode=%s rdcycle=%0d prepare=%0d start=%0d poll=%0d read=%0d check=%0d end_to_end=%0d self_test=%0d core=%0d polls=%0d stage_sum=%0d sim=%0d",
             INPUT_DIRECT ? "direct" : "buffered", dut.debug_regs[13],
             dut.debug_regs[3], dut.debug_regs[4], dut.debug_regs[5],
             dut.debug_regs[6], dut.debug_regs[7], dut.debug_regs[8],
             dut.debug_regs[9], dut.debug_regs[10], dut.debug_regs[11],
             dut.debug_regs[12], timeout_cycles);
    $finish;
  end
endmodule

module tb_mlkem_prepare_buffered;
  tb_mlkem_prepare_compare #(
      .INPUT_DIRECT(0), .FIRMWARE_FILE("prepare_buffered.mem")
  ) test();
endmodule

module tb_mlkem_prepare_direct;
  tb_mlkem_prepare_compare #(
      .INPUT_DIRECT(1), .FIRMWARE_FILE("prepare_direct.mem")
  ) test();
endmodule
