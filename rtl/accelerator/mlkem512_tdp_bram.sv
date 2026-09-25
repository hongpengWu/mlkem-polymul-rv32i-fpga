`timescale 1ns/1ps
// Two 16-bit ports, byte enables, one rising-edge read latency.
// Port ownership is selected outside the RAM: host while idle, HLS while busy.
// No array reset: the host must load every input before starting a job.
module mlkem512_tdp_bram #(parameter integer ADDR_BITS = 8) (
    input wire clk,
    input wire en0, input wire [1:0] we0,
    input wire [ADDR_BITS-1:0] addr0, input wire [15:0] d0,
    output reg [15:0] q0,
    input wire en1, input wire [1:0] we1,
    input wire [ADDR_BITS-1:0] addr1, input wire [15:0] d1,
    output reg [15:0] q1
);
    (* ram_style = "block" *) reg [15:0] mem [0:(1<<ADDR_BITS)-1];
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
