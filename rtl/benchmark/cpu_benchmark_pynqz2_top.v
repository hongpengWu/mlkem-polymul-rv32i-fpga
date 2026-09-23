`timescale 1ns/1ps
module cpu_benchmark_pynqz2_top #(
  parameter FIRMWARE_INIT_FILE = "cpu_baseline.mem",
  parameter ENABLE_VIO = 0,
  parameter CPU_ENABLE_MUL = 0,
  parameter CPU_ENABLE_FAST_MUL = 0,
  parameter CPU_ENABLE_DIV = 0
)(
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

  // Async assertion, synchronous release after clock lock or button release.
  wire reset_request = !locked || btn0;
  (* ASYNC_REG = "TRUE" *) reg [3:0] reset_sync = 0;
  always @(posedge clk100 or posedge reset_request)
    if (reset_request) reset_sync <= 0;
    else reset_sync <= {reset_sync[2:0],1'b1};

  wire [31:0] status;
  wire trap;
  wire done;
  wire [383:0] profile_words;
  cpu_benchmark_system #(
    .FIRMWARE_INIT_FILE(FIRMWARE_INIT_FILE),
    .CPU_ENABLE_MUL(CPU_ENABLE_MUL),
    .CPU_ENABLE_FAST_MUL(CPU_ENABLE_FAST_MUL),
    .CPU_ENABLE_DIV(CPU_ENABLE_DIV)
  ) system_i (
    .clk(clk100), .resetn(reset_sync[3]), .trap(trap),
    .status_out(status),
    .profile_words(profile_words)
  );
  assign done = status == 32'h600d600d;
  // Read-only probes: the original board configuration leaves this branch out.
  generate if (ENABLE_VIO) begin : debug_view
    mlkem_profile_vio profile_vio (
      .clk(clk100),
      .probe_in0(profile_words[31:0]),
      .probe_in1(profile_words[63:32]),
      .probe_in2(profile_words[95:64]),
      .probe_in3(profile_words[127:96]),
      .probe_in4(profile_words[159:128]),
      .probe_in5(profile_words[191:160]),
      .probe_in6(profile_words[223:192]),
      .probe_in7(profile_words[255:224]),
      .probe_in8(profile_words[287:256]),
      .probe_in9(profile_words[319:288]),
      .probe_in10(profile_words[351:320]),
      .probe_in11(profile_words[383:352]),
      .probe_in12({trap, done})
    );
  end endgenerate
  // CPU firmware checks checksums; simulation separately checks every coefficient.
  assign led[0] = status == 32'h600d600d;
  assign led[1] = status[31:16] == 16'hdead;
  assign led[2] = done;
  assign led[3] = trap;
endmodule
