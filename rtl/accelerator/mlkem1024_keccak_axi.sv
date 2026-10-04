`timescale 1ns/1ps

// PS-facing AXI4-Lite slave. RAM is owned by the host while RUN=0 and by
// the CPU while RUN=1. Finished/trapped CPU jobs permit host RAM reads.
// One transaction is outstanding: AW and W may arrive in either order,
// and every accepted request receives a buffered response, including errors.
module mlkem1024_keccak_axi #(
    parameter FIRMWARE_INIT_FILE = "ps_kat.mem"
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input wire s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 18, READ_WRITE_MODE READ_WRITE, HAS_BURST 0, HAS_LOCK 0, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, FREQ_HZ 100000000" *)
    input wire [17:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output reg [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [17:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output reg [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready,
    output wire [3:0] led
);
    localparam [31:0] STATUS_PASS=32'h4b415450, STATUS_FAIL=32'h4b415446;
    localparam [1:0] RESP_OKAY=2'b00, RESP_SLVERR=2'b10;
    reg run;
    reg aw_held, w_held, ram_read_pending;
    reg [17:0] awaddr_held;
    reg [31:0] wdata_held;
    reg [3:0] wstrb_held;
    wire core_resetn=s_axi_aresetn && run;
    wire trap;
    wire [31:0] status, hls_starts, hls_busy_cycles, buffer_writes, buffer_reads;
    wire [383:0] profile_words;
    wire finished=status==STATUS_PASS || status==STATUS_FAIL || trap;
    wire ram_read_allowed=!run || finished;

    // Neither write channel waits for the other. A pending read/response
    // blocks subsequent requests, so its data cannot change under backpressure.
    assign s_axi_awready=s_axi_aresetn && !aw_held && !s_axi_bvalid &&
                         !s_axi_rvalid && !ram_read_pending;
    assign s_axi_wready=s_axi_aresetn && !w_held && !s_axi_bvalid &&
                        !s_axi_rvalid && !ram_read_pending;
    assign s_axi_arready=s_axi_aresetn && !aw_held && !w_held && !s_axi_bvalid &&
                         !s_axi_rvalid && !ram_read_pending && !s_axi_awvalid && !s_axi_wvalid;
    wire aw_fire=s_axi_awvalid && s_axi_awready;
    wire w_fire=s_axi_wvalid && s_axi_wready;
    wire ar_fire=s_axi_arvalid && s_axi_arready;
    wire write_commit=s_axi_aresetn && !s_axi_bvalid &&
                      (aw_held || aw_fire) && (w_held || w_fire);
    wire [17:0] write_addr=aw_held ? awaddr_held : s_axi_awaddr;
    wire [31:0] write_data=w_held ? wdata_held : s_axi_wdata;
    wire [3:0] write_strb=w_held ? wstrb_held : s_axi_wstrb;
    wire write_aligned=write_addr[1:0]==0;
    wire write_ram=!write_addr[17];
    wire write_control=write_addr==18'h20008;
    wire write_allowed=write_aligned && ((write_ram && !run) || write_control);
    wire ram_write=write_commit && write_allowed && write_ram;
    wire ram_read=ar_fire && s_axi_araddr[1:0]==0 && !s_axi_araddr[17] && ram_read_allowed;
    wire [31:0] ram_rdata;

    mlkem1024_keccak_system #(
        .FIRMWARE_INIT_FILE(FIRMWARE_INIT_FILE),.RAM_ADDR_BITS(15),.ENABLE_HOST(1),
        .CPU_ENABLE_MUL(1),.CPU_ENABLE_FAST_MUL(1),.CPU_ENABLE_DIV(1)
    ) system_i (
        .clk(s_axi_aclk),.resetn(core_resetn),.trap(trap),
        .status_out(status),.profile_words(profile_words),
        .host_en(ram_write || ram_read),.host_we(ram_write ? write_strb : 4'b0),
        .host_addr(ram_write ? write_addr[16:2] : s_axi_araddr[16:2]),
        .host_din(write_data),.host_dout(ram_rdata),
        .hls_starts(hls_starts),.hls_busy_cycles(hls_busy_cycles),
        .buffer_writes(buffer_writes),.buffer_reads(buffer_reads)
    );

    wire passed=status==STATUS_PASS;
    wire failed=status==STATUS_FAIL || trap;
    assign led[0]=core_resetn && passed && !failed;
    assign led[1]=core_resetn && failed;
    assign led[2]=core_resetn && !passed && !failed;
    assign led[3]=core_resetn && trap;

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            run<=0; aw_held<=0; w_held<=0; ram_read_pending<=0;
            awaddr_held<=0; wdata_held<=0; wstrb_held<=0;
            s_axi_bvalid<=0; s_axi_bresp<=RESP_OKAY;
            s_axi_rvalid<=0; s_axi_rresp<=RESP_OKAY; s_axi_rdata<=0;
        end else begin
            if (aw_fire) begin aw_held<=1; awaddr_held<=s_axi_awaddr; end
            if (w_fire) begin w_held<=1; wdata_held<=s_axi_wdata; wstrb_held<=s_axi_wstrb; end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if (write_commit) begin
                aw_held<=0; w_held<=0; s_axi_bvalid<=1;
                s_axi_bresp<=write_allowed ? RESP_OKAY : RESP_SLVERR;
                if (write_allowed && write_control && write_strb[0]) run<=write_data[0];
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if (ar_fire) begin
                s_axi_rdata<=0; s_axi_rresp<=RESP_OKAY;
                if (ram_read) ram_read_pending<=1;
                else begin
                    s_axi_rvalid<=1;
                    if (s_axi_araddr[1:0]!=0) s_axi_rresp<=RESP_SLVERR;
                    else if (s_axi_araddr>=18'h20040 && s_axi_araddr<18'h20070)
                        s_axi_rdata<=profile_words[32*s_axi_araddr[5:2]+:32];
                    else case (s_axi_araddr)
                        18'h20000: s_axi_rdata<=32'h4b344158;
                        18'h20004: s_axi_rdata<=32'd1;
                        18'h20008: s_axi_rdata<={31'b0,run};
                        18'h2000c: s_axi_rdata<=status;
                        18'h20010: s_axi_rdata<={31'b0,trap};
                        18'h20014: s_axi_rdata<=32'd100000000;
                        18'h20018: s_axi_rdata<=32'd131072;
                        18'h2001c: s_axi_rdata<=0;
                        18'h20080: s_axi_rdata<=hls_starts;
                        18'h20084: s_axi_rdata<=hls_busy_cycles;
                        18'h20088: s_axi_rdata<=buffer_writes;
                        18'h2008c: s_axi_rdata<=buffer_reads;
                        default: s_axi_rresp<=RESP_SLVERR;
                    endcase
                end
            end
            // Port B's one-cycle synchronous output becomes available after
            // the acceptance edge. Capture it before asserting AXI RVALID.
            if (ram_read_pending) begin
                ram_read_pending<=0; s_axi_rvalid<=1;
                s_axi_rdata<=ram_rdata; s_axi_rresp<=RESP_OKAY;
            end
        end
    end
endmodule
