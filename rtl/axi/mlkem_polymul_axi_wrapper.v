`timescale 1ns / 1ps

// AXI4-Lite front end for the single-DSP HLS polynomial-multiplication core.
// Two 16-bit coefficients are packed into every 32-bit AXI data word.
module mlkem_polymul_axi_wrapper #(
    parameter integer C_S_AXI_ADDR_WIDTH = 16,
    parameter integer C_S_AXI_DATA_WIDTH = 32
)(
    input  wire                              s_axi_aclk,
    input  wire                              s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_awaddr,
    input  wire                              s_axi_awvalid,
    output wire                              s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]     s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  wire                              s_axi_wvalid,
    output wire                              s_axi_wready,
    output wire [1:0]                        s_axi_bresp,
    output reg                               s_axi_bvalid,
    input  wire                              s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_araddr,
    input  wire                              s_axi_arvalid,
    output wire                              s_axi_arready,
    output reg  [C_S_AXI_DATA_WIDTH-1:0]     s_axi_rdata,
    output wire [1:0]                        s_axi_rresp,
    output reg                               s_axi_rvalid,
    input  wire                              s_axi_rready,
    output wire                              interrupt
);

  localparam [15:0] REG_CONTROL = 16'h0000;
  localparam [15:0] REG_CYCLES  = 16'h0004;
  localparam [15:0] REG_ID      = 16'h0008;
  localparam [15:0] MEM_A_BASE  = 16'h1000;
  localparam [15:0] MEM_B_BASE  = 16'h1200;
  localparam [15:0] MEM_O_BASE  = 16'h1400;


  reg aw_hold, w_hold;
  reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_hold;
  reg [C_S_AXI_DATA_WIDTH-1:0] wdata_hold;
  reg [(C_S_AXI_DATA_WIDTH/8)-1:0] wstrb_hold;

  wire aw_fire = s_axi_awvalid && s_axi_awready;
  wire w_fire  = s_axi_wvalid  && s_axi_wready;
  wire [C_S_AXI_ADDR_WIDTH-1:0] commit_addr = aw_hold ? awaddr_hold : s_axi_awaddr;
  wire [C_S_AXI_DATA_WIDTH-1:0] commit_data = w_hold ? wdata_hold : s_axi_wdata;
  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] commit_strb = w_hold ? wstrb_hold : s_axi_wstrb;
  wire write_commit = !s_axi_bvalid &&
                      (aw_hold || aw_fire) && (w_hold || w_fire);

  assign s_axi_bresp   = 2'b00;
  assign s_axi_rresp   = 2'b00;

  reg ap_start;
  wire ap_done, ap_idle, ap_ready;
  reg busy, done_sticky, access_error;
  reg [31:0] cycle_count;
  assign interrupt = done_sticky;

  wire [7:0] a_address0, a_address1, b_address0, b_address1;
  wire a_ce0, a_ce1, b_ce0, b_ce1;
  wire [15:0] a_q0, a_q1, b_q0, b_q1;
  wire [7:0] output_r_address0;
  wire output_r_ce0, output_r_we0;
  wire [15:0] output_r_d0;

  reg clearing = 1'b1;
  reg [6:0] clear_index = 0;
  reg read_pending;
  reg [1:0] read_bank;
  wire read_a = s_axi_araddr >= MEM_A_BASE && s_axi_araddr < MEM_B_BASE;
  wire read_b = s_axi_araddr >= MEM_B_BASE && s_axi_araddr < MEM_O_BASE;
  wire read_o = s_axi_araddr >= MEM_O_BASE && s_axi_araddr < MEM_O_BASE + 16'h0200;
  wire read_memory = read_a || read_b || read_o;
  wire read_fire = s_axi_arvalid && s_axi_arready;
  wire write_a = write_commit && !busy && commit_addr >= MEM_A_BASE && commit_addr < MEM_B_BASE;
  wire write_b = write_commit && !busy && commit_addr >= MEM_B_BASE && commit_addr < MEM_O_BASE;
  wire [7:0] cpu_wr_lo = {commit_addr[8:2],1'b0};
  wire [7:0] cpu_rd_lo = {s_axi_araddr[8:2],1'b0};
  wire [7:0] clear_lo = {clear_index,1'b0};
  wire [15:0] o_q0, o_q1;

  assign s_axi_awready = !clearing && !aw_hold && !s_axi_bvalid;
  assign s_axi_wready = !clearing && !w_hold && !s_axi_bvalid;
  assign s_axi_arready = !clearing && !read_pending && !s_axi_rvalid &&
                        !(read_memory && (busy || aw_hold || w_hold || s_axi_awvalid || s_axi_wvalid));

  // HLS owns both input ports while busy; CPU memory reads wait for done.
  mlkem_coeff_tdp_ram a_ram(
    .clk(s_axi_aclk),
    .en0(clearing || a_ce0 || write_a || (read_fire && read_a)),
    .en1(clearing || a_ce1 || write_a || (read_fire && read_a)),
    .addr0(clearing ? clear_lo : busy ? a_address0 : write_a ? cpu_wr_lo : cpu_rd_lo),
    .addr1(clearing ? (clear_lo | 8'd1) : busy ? a_address1 : write_a ? (cpu_wr_lo | 8'd1) : (cpu_rd_lo | 8'd1)),
    .we0(clearing ? 2'b11 : write_a ? commit_strb[1:0] : 2'b00),
    .we1(clearing ? 2'b11 : write_a ? commit_strb[3:2] : 2'b00),
    .d0(clearing ? 16'd0 : commit_data[15:0]), .d1(clearing ? 16'd0 : commit_data[31:16]),
    .q0(a_q0), .q1(a_q1));
  mlkem_coeff_tdp_ram b_ram(
    .clk(s_axi_aclk),
    .en0(clearing || b_ce0 || write_b || (read_fire && read_b)),
    .en1(clearing || b_ce1 || write_b || (read_fire && read_b)),
    .addr0(clearing ? clear_lo : busy ? b_address0 : write_b ? cpu_wr_lo : cpu_rd_lo),
    .addr1(clearing ? (clear_lo | 8'd1) : busy ? b_address1 : write_b ? (cpu_wr_lo | 8'd1) : (cpu_rd_lo | 8'd1)),
    .we0(clearing ? 2'b11 : write_b ? commit_strb[1:0] : 2'b00),
    .we1(clearing ? 2'b11 : write_b ? commit_strb[3:2] : 2'b00),
    .d0(clearing ? 16'd0 : commit_data[15:0]), .d1(clearing ? 16'd0 : commit_data[31:16]),
    .q0(b_q0), .q1(b_q1));
  mlkem_coeff_tdp_ram o_ram(
    .clk(s_axi_aclk),
    .en0(clearing || output_r_ce0 || (read_fire && read_o)),
    .en1(clearing || (read_fire && read_o)),
    .addr0(clearing ? clear_lo : busy ? output_r_address0 : cpu_rd_lo),
    .addr1(clearing ? (clear_lo | 8'd1) : (cpu_rd_lo | 8'd1)),
    .we0(clearing ? 2'b11 : (output_r_ce0 && output_r_we0) ? 2'b11 : 2'b00),
    .we1(clearing ? 2'b11 : 2'b00),
    .d0(clearing ? 16'd0 : output_r_d0), .d1(16'd0),
    .q0(o_q0), .q1(o_q1));

  always @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      clearing <= 1'b1;
      clear_index <= 0;
    end else if (clearing) begin
      if (clear_index == 127) clearing <= 1'b0;
      else clear_index <= clear_index + 1'b1;
    end
  end

  always @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      aw_hold <= 1'b0;
      w_hold <= 1'b0;
      s_axi_bvalid <= 1'b0;
      s_axi_rvalid <= 1'b0;
      s_axi_rdata <= 32'b0;
      ap_start <= 1'b0;
      busy <= 1'b0;
      done_sticky <= 1'b0;
      access_error <= 1'b0;
      cycle_count <= 32'b0;
      read_pending <= 1'b0;
      read_bank <= 0;
    end else begin
      ap_start <= 1'b0;

      if (busy)
        cycle_count <= cycle_count + 1'b1;
      if (ap_done) begin
        busy <= 1'b0;
        done_sticky <= 1'b1;
      end


      if (aw_fire) begin
        aw_hold <= 1'b1;
        awaddr_hold <= s_axi_awaddr;
      end
      if (w_fire) begin
        w_hold <= 1'b1;
        wdata_hold <= s_axi_wdata;
        wstrb_hold <= s_axi_wstrb;
      end

      if (s_axi_bvalid && s_axi_bready)
        s_axi_bvalid <= 1'b0;

      if (write_commit) begin
        aw_hold <= 1'b0;
        w_hold <= 1'b0;
        s_axi_bvalid <= 1'b1;

        if (commit_addr == REG_CONTROL) begin
          if (commit_strb[0] && commit_data[1]) done_sticky <= 1'b0;
          if (commit_strb[0] && commit_data[2]) access_error <= 1'b0;
          if (commit_strb[0] && commit_data[0]) begin
            if (!busy && ap_idle) begin
              ap_start <= 1'b1;
              busy <= 1'b1;
              done_sticky <= 1'b0;
              cycle_count <= 32'b0;
            end else begin
              access_error <= 1'b1;
            end
          end
        end else if ((commit_addr >= MEM_A_BASE) && (commit_addr < MEM_A_BASE + 16'h0200)) begin
          if (busy) begin
            access_error <= 1'b1;
          end
        end else if ((commit_addr >= MEM_B_BASE) && (commit_addr < MEM_B_BASE + 16'h0200)) begin
          if (busy) begin
            access_error <= 1'b1;
          end
        end else begin
          access_error <= 1'b1;
        end
      end

      if (s_axi_rvalid && s_axi_rready)
        s_axi_rvalid <= 1'b0;
      if (read_pending) begin
        s_axi_rvalid <= 1'b1;
        read_pending <= 1'b0;
        case (read_bank)
          0: s_axi_rdata <= {a_q1,a_q0};
          1: s_axi_rdata <= {b_q1,b_q0};
          default: s_axi_rdata <= {o_q1,o_q0};
        endcase
      end
      if (read_fire) begin
        s_axi_rvalid <= !read_memory;
        if (s_axi_araddr == REG_CONTROL)
          s_axi_rdata <= {27'b0, access_error, busy, ap_idle, done_sticky, 1'b0};
        else if (s_axi_araddr == REG_CYCLES)
          s_axi_rdata <= cycle_count;
        else if (s_axi_araddr == REG_ID)
          s_axi_rdata <= 32'h5633_3945; // ASCII "V39E"
        else if (read_memory) begin
          read_pending <= 1'b1;
          read_bank <= read_a ? 0 : read_b ? 1 : 2;
        end else begin
          s_axi_rdata <= 32'b0;
          access_error <= 1'b1;
        end
      end
    end
  end

  mlkem_poly_mul256_v39e_true_one_dsp core (
    .ap_clk(s_axi_aclk),
    .ap_rst(!s_axi_aresetn),
    .ap_start(ap_start),
    .ap_done(ap_done),
    .ap_idle(ap_idle),
    .ap_ready(ap_ready),
    .a_address0(a_address0), .a_ce0(a_ce0), .a_q0(a_q0),
    .a_address1(a_address1), .a_ce1(a_ce1), .a_q1(a_q1),
    .b_address0(b_address0), .b_ce0(b_ce0), .b_q0(b_q0),
    .b_address1(b_address1), .b_ce1(b_ce1), .b_q1(b_q1),
    .output_r_address0(output_r_address0),
    .output_r_ce0(output_r_ce0),
    .output_r_we0(output_r_we0),
    .output_r_d0(output_r_d0)
  );

endmodule
