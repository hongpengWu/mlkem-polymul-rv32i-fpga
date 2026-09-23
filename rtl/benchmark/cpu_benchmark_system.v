`timescale 1ns/1ps
// CPU-only counterpart of the original profiling system. AXI local RAM/debug
// response pipeline is retained; there is no accelerator address target.
module cpu_benchmark_system #(
    parameter FIRMWARE_INIT_FILE = "cpu_baseline.mem",
    parameter integer RAM_ADDR_BITS = 12,
    parameter CPU_ENABLE_MUL = 0,
    parameter CPU_ENABLE_FAST_MUL = 0,
    parameter CPU_ENABLE_DIV = 0
)(
    input wire clk, resetn,
    output wire trap,
    output wire [31:0] status_out,
    output wire [383:0] profile_words
);
    localparam [31:0] RAM_LIMIT = (1 << (RAM_ADDR_BITS+2));
    localparam [31:0] DBG_BASE = 32'h50000000;
    reg [31:0] debug_regs[0:15];
    integer i, byte_i;
    initial for(i=0;i<16;i=i+1) debug_regs[i]=0;
    assign status_out=debug_regs[0];
    genvar p;
    generate for(p=0;p<12;p=p+1) begin: profile_export
        assign profile_words[32*p+:32]=debug_regs[p];
    end endgenerate

    wire c_awvalid,c_awready,c_wvalid,c_wready,c_bvalid,c_bready;
    wire c_arvalid,c_arready,c_rvalid,c_rready;
    wire [31:0] c_awaddr,c_wdata,c_araddr,c_rdata;
    wire [3:0] c_wstrb;
    picorv32_axi #(
        .ENABLE_COUNTERS(1),.ENABLE_COUNTERS64(0),
        .ENABLE_MUL(CPU_ENABLE_MUL),.ENABLE_FAST_MUL(CPU_ENABLE_FAST_MUL),
        .ENABLE_DIV(CPU_ENABLE_DIV),.ENABLE_TRACE(1),.REGS_INIT_ZERO(1),
        .STACKADDR(RAM_LIMIT-16)
    ) cpu (
        .clk(clk),.resetn(resetn),.trap(trap),
        .mem_axi_awvalid(c_awvalid),.mem_axi_awready(c_awready),.mem_axi_awaddr(c_awaddr),.mem_axi_awprot(),
        .mem_axi_wvalid(c_wvalid),.mem_axi_wready(c_wready),.mem_axi_wdata(c_wdata),.mem_axi_wstrb(c_wstrb),
        .mem_axi_bvalid(c_bvalid),.mem_axi_bready(c_bready),
        .mem_axi_arvalid(c_arvalid),.mem_axi_arready(c_arready),.mem_axi_araddr(c_araddr),.mem_axi_arprot(),
        .mem_axi_rvalid(c_rvalid),.mem_axi_rready(c_rready),.mem_axi_rdata(c_rdata),
        .pcpi_wr(1'b0),.pcpi_rd(32'b0),.pcpi_wait(1'b0),.pcpi_ready(1'b0),
        .irq(32'b0),.eoi(),.trace_valid(),.trace_data()
    );
    wire write_sel_ram=c_awaddr<RAM_LIMIT;
    wire read_sel_ram=c_araddr<RAM_LIMIT;
    wire write_sel_dbg=c_awaddr[31:6]==DBG_BASE[31:6];
    wire read_sel_dbg=c_araddr[31:6]==DBG_BASE[31:6];
    reg local_aw_hold,local_w_hold,local_bvalid,local_rvalid,local_read_is_ram;
    reg [31:0] local_awaddr,local_wdata,local_rdata;
    reg [3:0] local_wstrb;
    wire [31:0] boot_rdata;
    wire local_awready=!local_aw_hold && !local_bvalid;
    wire local_wready=!local_w_hold && !local_bvalid;
    wire local_arready=!local_rvalid;
    wire local_aw_fire=c_awvalid && c_awready;
    wire local_w_fire=c_wvalid && c_wready;
    wire local_write_commit=!local_bvalid &&
        (local_aw_hold || local_aw_fire) && (local_w_hold || local_w_fire);
    wire [31:0] commit_addr=local_aw_hold ? local_awaddr : c_awaddr;
    wire [31:0] commit_data=local_w_hold ? local_wdata : c_wdata;
    wire [3:0] commit_strb=local_w_hold ? local_wstrb : c_wstrb;
    assign c_awready=(write_sel_ram || write_sel_dbg) && local_awready;
    assign c_wready=(write_sel_ram || write_sel_dbg) && local_wready;
    assign c_bvalid=local_bvalid;
    assign c_arready=(read_sel_ram || read_sel_dbg) && local_arready;
    assign c_rvalid=local_rvalid;
    assign c_rdata=local_read_is_ram ? boot_rdata : local_rdata;
    wire boot_write=local_write_commit && commit_addr<RAM_LIMIT;
    wire boot_read=c_arvalid && c_arready && read_sel_ram;
    wire [RAM_ADDR_BITS-1:0] boot_addr=boot_write ? commit_addr[RAM_ADDR_BITS+1:2] : c_araddr[RAM_ADDR_BITS+1:2];
    xpm_memory_spram #(
        .ADDR_WIDTH_A(RAM_ADDR_BITS),.AUTO_SLEEP_TIME(0),.BYTE_WRITE_WIDTH_A(8),
        .CASCADE_HEIGHT(0),.ECC_MODE("no_ecc"),.MEMORY_INIT_FILE(FIRMWARE_INIT_FILE),
        .MEMORY_INIT_PARAM("0"),.MEMORY_OPTIMIZATION("true"),.MEMORY_PRIMITIVE("block"),
        .MEMORY_SIZE(32*(1<<RAM_ADDR_BITS)),.MESSAGE_CONTROL(0),.READ_DATA_WIDTH_A(32),
        .READ_LATENCY_A(1),.READ_RESET_VALUE_A("0"),.RST_MODE_A("SYNC"),.SIM_ASSERT_CHK(0),
        .USE_MEM_INIT(1),.WAKEUP_TIME("disable_sleep"),.WRITE_DATA_WIDTH_A(32),.WRITE_MODE_A("read_first")
    ) firmware_bram (
        .clka(clk),.ena(boot_write || boot_read),.addra(boot_addr),.dina(commit_data),
        .wea(boot_write ? commit_strb : 4'b0000),.douta(boot_rdata),
        .rsta(1'b0),.regcea(1'b1),.sleep(1'b0),.injectsbiterra(1'b0),.injectdbiterra(1'b0),
        .sbiterra(),.dbiterra()
    );
    always @(posedge clk) begin
        if(!resetn) begin
            local_aw_hold<=0;local_w_hold<=0;local_bvalid<=0;local_rvalid<=0;
            local_rdata<=0;local_read_is_ram<=0;
            for(i=0;i<16;i=i+1) debug_regs[i]<=0;
        end else begin
            if(local_aw_fire) begin local_aw_hold<=1;local_awaddr<=c_awaddr;end
            if(local_w_fire) begin local_w_hold<=1;local_wdata<=c_wdata;local_wstrb<=c_wstrb;end
            if(local_bvalid && c_bready) local_bvalid<=0;
            if(local_write_commit) begin
                local_aw_hold<=0;local_w_hold<=0;local_bvalid<=1;
                if(commit_addr[31:6]==DBG_BASE[31:6])
                    for(byte_i=0;byte_i<4;byte_i=byte_i+1)
                        if(commit_strb[byte_i]) debug_regs[commit_addr[5:2]][8*byte_i+:8]<=commit_data[8*byte_i+:8];
            end
            if(local_rvalid && c_rready) local_rvalid<=0;
            if(c_arvalid && c_arready) begin
                local_rvalid<=1;local_read_is_ram<=read_sel_ram;
                local_rdata<=read_sel_dbg ? debug_regs[c_araddr[5:2]] : 32'b0;
            end
        end
    end
endmodule
