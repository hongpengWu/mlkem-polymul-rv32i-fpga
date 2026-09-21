`timescale 1ns/1ps
// Two synchronous ports with native byte enables; contents have no reset.
module mlkem_coeff_tdp_ram(
  input wire clk, en0, en1,
  input wire [7:0] addr0, addr1,
  input wire [1:0] we0, we1,
  input wire [15:0] d0, d1,
  output reg [15:0] q0, q1
);
  (* ram_style = "block" *) reg [15:0] mem [0:255];
  always @(posedge clk) if (en0) begin
    if (we0[0]) mem[addr0][7:0] <= d0[7:0];
    if (we0[1]) mem[addr0][15:8] <= d0[15:8];
    q0 <= mem[addr0];
  end
  always @(posedge clk) if (en1) begin
    if (we1[0]) mem[addr1][7:0] <= d1[7:0];
    if (we1[1]) mem[addr1][15:8] <= d1[15:8];
    q1 <= mem[addr1];
  end
endmodule
