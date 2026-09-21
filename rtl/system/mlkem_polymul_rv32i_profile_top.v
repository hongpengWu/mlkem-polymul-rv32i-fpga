`timescale 1ns / 1ps

// Standalone RV32I profiling system for the ML-KEM polynomial multiplier.
module mlkem_polymul_rv32i_profile_top #(
    parameter FIRMWARE_INIT_FILE = "profile_firmware.mem"
) (
    input  wire        clk,
    input  wire        resetn,
    output wire        trap,
    output wire        trace_valid,
    output wire [35:0] trace_data,
    output wire        accel_interrupt,
    output wire [31:0] status_out,
    output wire [383:0] profile_words
);
  localparam [31:0] RAM_LIMIT = 32'h0000_1000;
  localparam [31:0] ACCEL_BASE = 32'h4000_0000;
  localparam [31:0] DBG_BASE  = 32'h5000_0000;

  reg [31:0] debug_regs [0:15];
  integer init_i;
  integer byte_i;

  initial begin
    for (init_i = 0; init_i < 16; init_i = init_i + 1)
      debug_regs[init_i] = 32'b0;
  end

  assign status_out = debug_regs[0];
  genvar profile_index;
  generate for (profile_index = 0; profile_index < 12; profile_index = profile_index + 1) begin : profile_export
    assign profile_words[32*profile_index +: 32] = debug_regs[profile_index];
  end endgenerate

  wire c_awvalid, c_awready, c_wvalid, c_wready, c_bvalid, c_bready;
  wire [31:0] c_awaddr, c_wdata;
  wire [3:0] c_wstrb;
  wire [2:0] c_awprot;
  wire c_arvalid, c_arready, c_rvalid, c_rready;
  wire [31:0] c_araddr, c_rdata;
  wire [2:0] c_arprot;

  picorv32_axi #(
      .ENABLE_COUNTERS(1),
      .ENABLE_COUNTERS64(0),
      .ENABLE_MUL(0),
      .ENABLE_TRACE(1),
      .REGS_INIT_ZERO(1),
      .STACKADDR(32'h0000_0ff0)
  ) cpu (
      .clk(clk), .resetn(resetn), .trap(trap),
      .mem_axi_awvalid(c_awvalid), .mem_axi_awready(c_awready),
      .mem_axi_awaddr(c_awaddr), .mem_axi_awprot(c_awprot),
      .mem_axi_wvalid(c_wvalid), .mem_axi_wready(c_wready),
      .mem_axi_wdata(c_wdata), .mem_axi_wstrb(c_wstrb),
      .mem_axi_bvalid(c_bvalid), .mem_axi_bready(c_bready),
      .mem_axi_arvalid(c_arvalid), .mem_axi_arready(c_arready),
      .mem_axi_araddr(c_araddr), .mem_axi_arprot(c_arprot),
      .mem_axi_rvalid(c_rvalid), .mem_axi_rready(c_rready),
      .mem_axi_rdata(c_rdata),
      .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
      .irq(32'b0), .eoi(),
      .trace_valid(trace_valid), .trace_data(trace_data)
  );

  wire write_sel_ip = (c_awaddr[31:16] == ACCEL_BASE[31:16]);
  wire read_sel_ip  = (c_araddr[31:16] == ACCEL_BASE[31:16]);
  wire write_sel_ram = (c_awaddr < RAM_LIMIT);
  wire read_sel_ram  = (c_araddr < RAM_LIMIT);
  wire write_sel_dbg = (c_awaddr[31:6] == DBG_BASE[31:6]);
  wire read_sel_dbg  = (c_araddr[31:6] == DBG_BASE[31:6]);

  reg write_target_ip;
  reg read_target_ip;
  reg local_aw_hold, local_w_hold, local_bvalid;
  reg [31:0] local_awaddr, local_wdata;
  reg [3:0] local_wstrb;
  reg local_rvalid;
  reg [31:0] local_rdata;
  reg local_read_is_ram;
  wire [31:0] boot_rdata;

  wire local_awready = !local_aw_hold && !local_bvalid;
  wire local_wready  = !local_w_hold  && !local_bvalid;
  wire local_arready = !local_rvalid;
  wire local_aw_fire = c_awvalid && !write_sel_ip && local_awready;
  wire local_w_fire  = c_wvalid  && !write_sel_ip && local_wready;
  wire local_write_commit = !local_bvalid &&
                            (local_aw_hold || local_aw_fire) &&
                            (local_w_hold  || local_w_fire);
  wire [31:0] commit_addr = local_aw_hold ? local_awaddr : c_awaddr;
  wire [31:0] commit_data = local_w_hold ? local_wdata : c_wdata;
  wire [3:0] commit_strb = local_w_hold ? local_wstrb : c_wstrb;

  wire ip_awready, ip_wready, ip_bvalid, ip_arready, ip_rvalid;
  wire [1:0] ip_bresp, ip_rresp;
  wire [31:0] ip_rdata;

  wire ip_awvalid = c_awvalid && write_sel_ip;
  wire ip_wvalid  = c_wvalid  && write_sel_ip;
  wire ip_arvalid = c_arvalid && read_sel_ip;
  wire ip_bready  = c_bready && write_target_ip;
  wire ip_rready  = c_rready && read_target_ip;

  assign c_awready = write_sel_ip ? ip_awready :
                     ((write_sel_ram || write_sel_dbg) ? local_awready : 1'b0);
  assign c_wready  = write_sel_ip ? ip_wready :
                     ((write_sel_ram || write_sel_dbg) ? local_wready : 1'b0);
  assign c_bvalid  = write_target_ip ? ip_bvalid : local_bvalid;

  assign c_arready = read_sel_ip ? ip_arready :
                     ((read_sel_ram || read_sel_dbg) ? local_arready : 1'b0);
  assign c_rvalid  = read_target_ip ? ip_rvalid : local_rvalid;
  assign c_rdata   = read_target_ip ? ip_rdata :
                     (local_read_is_ram ? boot_rdata : local_rdata);

  wire boot_write = local_write_commit && (commit_addr < RAM_LIMIT);
  wire boot_read = c_arvalid && c_arready && read_sel_ram;
  wire [9:0] boot_addr = boot_write ? commit_addr[11:2] : c_araddr[11:2];

  xpm_memory_spram #(
      .ADDR_WIDTH_A(10),
      .AUTO_SLEEP_TIME(0),
      .BYTE_WRITE_WIDTH_A(8),
      .CASCADE_HEIGHT(0),
      .ECC_MODE("no_ecc"),
      .MEMORY_INIT_FILE(FIRMWARE_INIT_FILE),
      .MEMORY_INIT_PARAM("0"),
      .MEMORY_OPTIMIZATION("true"),
      .MEMORY_PRIMITIVE("block"),
      .MEMORY_SIZE(32768),
      .MESSAGE_CONTROL(0),
      .READ_DATA_WIDTH_A(32),
      .READ_LATENCY_A(1),
      .READ_RESET_VALUE_A("0"),
      .RST_MODE_A("SYNC"),
      .SIM_ASSERT_CHK(0),
      .USE_MEM_INIT(1),
      .WAKEUP_TIME("disable_sleep"),
      .WRITE_DATA_WIDTH_A(32),
      .WRITE_MODE_A("read_first")
  ) firmware_bram (
      .clka(clk), .ena(boot_write || boot_read),
      .addra(boot_addr), .dina(commit_data),
      .wea(boot_write ? commit_strb : 4'b0000),
      .douta(boot_rdata),
      .rsta(1'b0), .regcea(1'b1), .sleep(1'b0),
      .injectsbiterra(1'b0), .injectdbiterra(1'b0),
      .sbiterra(), .dbiterra()
  );

  always @(posedge clk) begin
    if (!resetn) begin
      write_target_ip <= 1'b0;
      read_target_ip <= 1'b0;
      local_aw_hold <= 1'b0;
      local_w_hold <= 1'b0;
      local_bvalid <= 1'b0;
      local_rvalid <= 1'b0;
      local_rdata <= 32'b0;
      local_read_is_ram <= 1'b0;
      for (init_i = 0; init_i < 16; init_i = init_i + 1)
        debug_regs[init_i] <= 32'b0;
    end else begin
      if (c_awvalid && c_awready)
        write_target_ip <= write_sel_ip;
      if (c_arvalid && c_arready)
        read_target_ip <= read_sel_ip;

      if (local_aw_fire) begin
        local_aw_hold <= 1'b1;
        local_awaddr <= c_awaddr;
      end
      if (local_w_fire) begin
        local_w_hold <= 1'b1;
        local_wdata <= c_wdata;
        local_wstrb <= c_wstrb;
      end
      if (local_bvalid && c_bready && !write_target_ip)
        local_bvalid <= 1'b0;

      if (local_write_commit) begin
        local_aw_hold <= 1'b0;
        local_w_hold <= 1'b0;
        local_bvalid <= 1'b1;
        if (commit_addr[31:6] == DBG_BASE[31:6]) begin
          for (byte_i = 0; byte_i < 4; byte_i = byte_i + 1)
            if (commit_strb[byte_i])
              debug_regs[commit_addr[5:2]][8*byte_i +: 8] <=
                  commit_data[8*byte_i +: 8];
        end
      end

      if (local_rvalid && c_rready && !read_target_ip)
        local_rvalid <= 1'b0;
      if (c_arvalid && c_arready && !read_sel_ip) begin
        local_rvalid <= 1'b1;
        local_read_is_ram <= read_sel_ram;
        if (read_sel_dbg)
          local_rdata <= debug_regs[c_araddr[5:2]];
        else
          local_rdata <= 32'b0;
      end
    end
  end

  mlkem_polymul_axi_wrapper accel (
      .s_axi_aclk(clk), .s_axi_aresetn(resetn),
      .s_axi_awaddr(c_awaddr[15:0]),
      .s_axi_awvalid(ip_awvalid), .s_axi_awready(ip_awready),
      .s_axi_wdata(c_wdata), .s_axi_wstrb(c_wstrb),
      .s_axi_wvalid(ip_wvalid), .s_axi_wready(ip_wready),
      .s_axi_bresp(ip_bresp), .s_axi_bvalid(ip_bvalid), .s_axi_bready(ip_bready),
      .s_axi_araddr(c_araddr[15:0]),
      .s_axi_arvalid(ip_arvalid), .s_axi_arready(ip_arready),
      .s_axi_rdata(ip_rdata), .s_axi_rresp(ip_rresp),
      .s_axi_rvalid(ip_rvalid), .s_axi_rready(ip_rready),
      .interrupt(accel_interrupt)
  );
endmodule
