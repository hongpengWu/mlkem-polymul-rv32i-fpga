`timescale 1ns/1ps
// One native request is accepted at each valid && ready edge. Reads return a
// one-cycle rvalid pulse. Control writes finish internally at the AXI B response
// before another native request is accepted; AW and W are independent channels.
//
// BASE + 0000..003f: generated HLS AXI-Lite registers, including COR ap_done.
// BASE + 0100/0104: cumulative starts / start-to-observed-completion cycles.
// BASE + 0108/010c: cumulative accepted CPU buffer writes / reads (context too).
// BASE + 0110: bit0 busy, bit1 sticky done, bit2 sticky error; W1C bits1/2.
// BASE + 1000..17ff: input, 2000..2fff: output, 3000..30cf: context.
// Buffers are little-endian and byte-writeable; context has 26 64-bit words.
// Reset clears control only. Firmware must initialize the buffers it consumes.
// Busy buffer accesses and unsupported/misaligned requests are acknowledged
// without touching memory (reads return zero), and set sticky error.
//
// Firmware uses single-shot operation, GIE=1/IER=1, and clears a pending ISR
// before each start. This provides completion without consuming COR ap_done.
// When interrupts are disabled, a CPU control read observing done releases busy.
// No private control reads are issued. Auto-restart and starting while busy are
// rejected because they would violate the explicit CPU/HLS memory ownership.
module keccak_mmio_adapter #(
    parameter [31:0] BASE_ADDR = 32'h5001_0000
) (
    input wire clk, resetn,
    input wire bus_valid, bus_write,
    input wire [31:0] bus_addr, bus_wdata,
    input wire [3:0] bus_wstrb,
    output wire bus_ready,
    output reg bus_rvalid,
    output reg [31:0] bus_rdata,
    output wire accel_busy, accel_done, accel_error,
    output wire [31:0] transaction_count, hls_cycles,
    output wire [31:0] buffer_writes, buffer_reads
);
    localparam [2:0] IDLE=0, CONTROL_WRITE=1, CONTROL_READ_ADDR=2,
                     CONTROL_READ_RESP=3, LOCAL_READ=4;
    reg [2:0] state;
    reg busy, done, error;
    reg [31:0] starts_reg, cycles_reg, writes_reg, reads_reg;
    reg count_cycles, irq_armed;
    reg gie_shadow;
    reg [1:0] ier_shadow;
    reg [7:0] command_shadow;
    wire [31:0] offset;
    wire hit;
    generate if (BASE_ADDR[13:0] == 0) begin: aligned_decode
        // A 16 KiB aligned window needs no subtractor in the ready path.
        // Outside this window, offset is ignored because fire is false.
        assign offset = {18'b0, bus_addr[13:0]};
        assign hit = bus_addr[31:14] == BASE_ADDR[31:14];
    end else begin: general_decode
        // Retain the parameterized semantics for unaligned base addresses.
        assign offset = bus_addr - BASE_ADDR;
        assign hit = bus_addr >= BASE_ADDR && offset < 32'h4000;
    end endgenerate
    wire aligned = offset[1:0] == 2'b00;
    wire control_window = offset < 32'h40;
    wire input_window = offset >= 32'h1000 && offset < 32'h1800;
    wire output_window = offset >= 32'h2000 && offset < 32'h3000;
    wire context_window = offset >= 32'h3000 && offset < 32'h30d0;
    wire buffer_window = input_window || output_window || context_window;
    wire metrics_window = offset >= 32'h100 && offset <= 32'h110;
    wire start_request = control_window && offset[5:0] == 6'h00 &&
                         bus_wstrb[0] && bus_wdata[0];
    wire auto_restart_request = control_window && offset[5:0] == 6'h00 &&
                                bus_wstrb[0] && bus_wdata[7];
    wire good_control_write = control_window && !auto_restart_request &&
                              !(start_request && busy);
    assign bus_ready = resetn && hit && state == IDLE && !bus_rvalid;
    wire fire = bus_valid && bus_ready;
    wire host_memory_access = fire && aligned && buffer_window && !busy;
    wire host_write = host_memory_access && bus_write;
    wire host_read = host_memory_access && !bus_write;
    assign accel_busy = busy;
    assign accel_done = done;
    assign accel_error = error;
    assign transaction_count = starts_reg;
    assign hls_cycles = cycles_reg;
    assign buffer_writes = writes_reg;
    assign buffer_reads = reads_reg;

    reg [5:0] control_addr;
    reg [31:0] control_wdata;
    reg [3:0] control_wstrb;
    reg aw_pending, w_pending;
    wire hls_awready, hls_wready, hls_bvalid, hls_arready, hls_rvalid;
    wire [1:0] hls_bresp, hls_rresp;
    wire [31:0] hls_rdata;
    wire hls_interrupt;
    wire hls_awvalid = state == CONTROL_WRITE && aw_pending;
    wire hls_wvalid = state == CONTROL_WRITE && w_pending;
    wire hls_bready = state == CONTROL_WRITE && !aw_pending && !w_pending;
    wire hls_arvalid = state == CONTROL_READ_ADDR;
    wire hls_rready = state == CONTROL_READ_RESP;
    wire hls_write_fire = hls_wvalid && hls_wready;
    // Only the done interrupt is used for ownership. Enabling the ready
    // interrupt as well requires control polling, since its cause is ambiguous.
    wire done_irq_enabled = gie_shadow && ier_shadow == 2'b01;

    wire [31:0] input_addr, output_addr, context_addr;
    wire input_en, output_en, context_en;
    wire [3:0] input_we, output_we;
    wire [7:0] context_we;
    wire [31:0] input_din, output_din;
    wire [63:0] context_din;
    reg [31:0] input_q, output_q;
    reg [63:0] context_q;
    mlkem1024_keccak_accel hls_i (
        .ap_clk(clk), .ap_rst_n(resetn),
        .input_r_Addr_A(input_addr), .input_r_EN_A(input_en),
        .input_r_WEN_A(input_we), .input_r_Din_A(input_din),
        .input_r_Dout_A(input_q), .input_r_Clk_A(), .input_r_Rst_A(),
        .output_r_Addr_A(output_addr), .output_r_EN_A(output_en),
        .output_r_WEN_A(output_we), .output_r_Din_A(output_din),
        .output_r_Dout_A(output_q), .output_r_Clk_A(), .output_r_Rst_A(),
        .context_r_Addr_A(context_addr), .context_r_EN_A(context_en),
        .context_r_WEN_A(context_we), .context_r_Din_A(context_din),
        .context_r_Dout_A(context_q), .context_r_Clk_A(), .context_r_Rst_A(),
        .s_axi_control_AWVALID(hls_awvalid), .s_axi_control_AWREADY(hls_awready),
        .s_axi_control_AWADDR(control_addr), .s_axi_control_WVALID(hls_wvalid),
        .s_axi_control_WREADY(hls_wready), .s_axi_control_WDATA(control_wdata),
        .s_axi_control_WSTRB(control_wstrb),
        .s_axi_control_BVALID(hls_bvalid), .s_axi_control_BREADY(hls_bready),
        .s_axi_control_BRESP(hls_bresp), .s_axi_control_ARVALID(hls_arvalid),
        .s_axi_control_ARREADY(hls_arready), .s_axi_control_ARADDR(control_addr),
        .s_axi_control_RVALID(hls_rvalid), .s_axi_control_RREADY(hls_rready),
        .s_axi_control_RDATA(hls_rdata), .s_axi_control_RRESP(hls_rresp),
        .interrupt(hls_interrupt)
    );

    // The generated Addr_A expressions explicitly shift word indices by 2/3.
    // Convert those byte addresses to native memory indices. A single muxed
    // synchronous port per buffer preserves the HLS BRAM latency of one cycle.
    (* ram_style = "block" *) reg [31:0] input_mem [0:511];
    (* ram_style = "block" *) reg [31:0] output_mem [0:1023];
    (* ram_style = "block" *) reg [63:0] context_mem [0:25];
    wire input_hls_good = input_addr < 32'h800 && input_addr[1:0] == 0;
    wire output_hls_good = output_addr < 32'h1000 && output_addr[1:0] == 0;
    wire context_hls_good = context_addr < 32'hd0 && context_addr[2:0] == 0;
    // HLS CLEAR's pipelined loop keeps EN asserted on the i==26 exit test,
    // with WEN=0. This unused one-past read must not access the 26-word RAM.
    // Suppress exactly that generated exit probe; all other bad accesses fault.
    wire context_clear_exit_probe = command_shadow == 8'd2 &&
                                   context_addr == 32'hd0 && context_we == 0;
    wire input_port_en = busy ? input_en && input_hls_good : host_memory_access && input_window;
    wire output_port_en = busy ? output_en && output_hls_good : host_memory_access && output_window;
    wire context_port_en = busy ? context_en && context_hls_good : host_memory_access && context_window;
    wire [8:0] input_port_addr = busy ? input_addr[10:2] : offset[10:2];
    wire [9:0] output_port_addr = busy ? output_addr[11:2] : offset[11:2];
    wire [4:0] context_port_addr = busy ? context_addr[7:3] : offset[7:3];
    wire [3:0] input_port_we = busy ? input_we : (host_write ? bus_wstrb : 4'b0);
    wire [3:0] output_port_we = busy ? output_we : (host_write ? bus_wstrb : 4'b0);
    wire [7:0] context_host_we = offset[2] ? {bus_wstrb,4'b0} : {4'b0,bus_wstrb};
    wire [7:0] context_port_we = busy ? context_we : (host_write ? context_host_we : 8'b0);
    wire [31:0] input_port_data = busy ? input_din : bus_wdata;
    wire [31:0] output_port_data = busy ? output_din : bus_wdata;
    wire [63:0] context_port_data = busy ? context_din : {bus_wdata,bus_wdata};
    integer byte_lane;
    always @(posedge clk) begin
        if (input_port_en) begin
            input_q <= input_mem[input_port_addr];
            for (byte_lane=0; byte_lane<4; byte_lane=byte_lane+1)
                if (input_port_we[byte_lane])
                    input_mem[input_port_addr][8*byte_lane+:8] <= input_port_data[8*byte_lane+:8];
        end
        if (output_port_en) begin
            output_q <= output_mem[output_port_addr];
            for (byte_lane=0; byte_lane<4; byte_lane=byte_lane+1)
                if (output_port_we[byte_lane])
                    output_mem[output_port_addr][8*byte_lane+:8] <= output_port_data[8*byte_lane+:8];
        end
        if (context_port_en) begin
            context_q <= context_mem[context_port_addr];
            for (byte_lane=0; byte_lane<8; byte_lane=byte_lane+1)
                if (context_port_we[byte_lane])
                    context_mem[context_port_addr][8*byte_lane+:8] <= context_port_data[8*byte_lane+:8];
        end
    end

    reg [1:0] local_read_buffer;
    reg local_read_high;
    reg [31:0] local_read_data;
    always @(posedge clk) begin
        if (!resetn) begin
            state <= IDLE;
            busy <= 0; done <= 0; error <= 0;
            starts_reg <= 0; cycles_reg <= 0; writes_reg <= 0; reads_reg <= 0;
            count_cycles <= 0; irq_armed <= 0; gie_shadow <= 0; ier_shadow <= 0;
            command_shadow <= 0;
            bus_rvalid <= 0; bus_rdata <= 0;
            control_addr <= 0; control_wdata <= 0; control_wstrb <= 0;
            aw_pending <= 0; w_pending <= 0;
            local_read_buffer <= 0; local_read_high <= 0; local_read_data <= 0;
        end else begin
            bus_rvalid <= 0;
            if (count_cycles) cycles_reg <= cycles_reg + 1;
            if (busy && !hls_interrupt) irq_armed <= 1;
            if (busy && done_irq_enabled && irq_armed && hls_interrupt) begin
                busy <= 0; done <= 1; count_cycles <= 0;
            end
            if (busy && ((input_en && !input_hls_good) ||
                         (output_en && !output_hls_good) ||
                         (context_en && !context_hls_good && !context_clear_exit_probe))) error <= 1;
            if (host_write) writes_reg <= writes_reg + 1;
            if (host_read) reads_reg <= reads_reg + 1;

            case (state)
                IDLE: if (fire) begin
                    if (bus_write) begin
                        if (aligned && good_control_write) begin
                            control_addr <= offset[5:0];
                            control_wdata <= bus_wdata;
                            control_wstrb <= bus_wstrb;
                            aw_pending <= 1; w_pending <= 1;
                            state <= CONTROL_WRITE;
                            if (start_request) begin
                                busy <= 1; done <= 0;
                                irq_armed <= !hls_interrupt;
                            end
                        end else if (aligned && offset == 32'h110) begin
                            if (bus_wstrb[0] && bus_wdata[1]) done <= 0;
                            if (bus_wstrb[0] && bus_wdata[2]) error <= 0;
                        end else if (!host_write) error <= 1;
                    end else if (aligned && control_window) begin
                        control_addr <= offset[5:0];
                        state <= CONTROL_READ_ADDR;
                    end else begin
                        local_read_buffer <= 0;
                        local_read_high <= offset[2];
                        local_read_data <= 0;
                        state <= LOCAL_READ;
                        if (host_read) begin
                            if (input_window) local_read_buffer <= 1;
                            else if (output_window) local_read_buffer <= 2;
                            else local_read_buffer <= 3;
                        end else if (aligned && metrics_window) begin
                            case (offset)
                                32'h100: local_read_data <= starts_reg;
                                32'h104: local_read_data <= cycles_reg;
                                32'h108: local_read_data <= writes_reg;
                                32'h10c: local_read_data <= reads_reg;
                                32'h110: local_read_data <= {29'b0,error,done,busy};
                                default: local_read_data <= 0;
                            endcase
                        end else error <= 1;
                    end
                end
                CONTROL_WRITE: begin
                    if (hls_awvalid && hls_awready) aw_pending <= 0;
                    if (hls_write_fire) begin
                        w_pending <= 0;
                        if (control_wstrb[0]) begin
                            if (control_addr == 6'h00 && control_wdata[0]) begin
                                starts_reg <= starts_reg + 1;
                                count_cycles <= 1;
                            end
                            if (control_addr == 6'h04) gie_shadow <= control_wdata[0];
                            if (control_addr == 6'h08) ier_shadow <= control_wdata[1:0];
                            if (control_addr == 6'h30) command_shadow <= control_wdata[7:0];
                        end
                    end
                    if (hls_bvalid && hls_bready) begin
                        state <= IDLE;
                        if (hls_bresp != 2'b00) begin
                            error <= 1;
                            if (control_addr == 0 && control_wstrb[0] && control_wdata[0]) begin
                                busy <= 0; count_cycles <= 0;
                            end
                        end
                    end
                end
                CONTROL_READ_ADDR: if (hls_arvalid && hls_arready)
                    state <= CONTROL_READ_RESP;
                CONTROL_READ_RESP: if (hls_rvalid && hls_rready) begin
                    bus_rdata <= hls_rdata;
                    bus_rvalid <= 1;
                    state <= IDLE;
                    if (hls_rresp != 2'b00) error <= 1;
                    else if (control_addr == 0 && hls_rdata[1] && !done_irq_enabled) begin
                        busy <= 0; done <= 1; count_cycles <= 0;
                    end
                end
                LOCAL_READ: begin
                    case (local_read_buffer)
                        1: bus_rdata <= input_q;
                        2: bus_rdata <= output_q;
                        3: bus_rdata <= local_read_high ? context_q[63:32] : context_q[31:0];
                        default: bus_rdata <= local_read_data;
                    endcase
                    bus_rvalid <= 1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
