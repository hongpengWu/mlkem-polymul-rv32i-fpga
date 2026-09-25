`timescale 1ns/1ps
// Native request/response bus. Each valid && ready edge accepts ONE request.
// Reads respond with a one-cycle rvalid pulse; there is no response backpressure.
// 32-bit aligned, little-endian packed int16. Base=0x50001000, offsets:
// A0=000 A1=200 B0=400 B1=600 cache0=800 cache1=900 result=a00..bff.
// CONTROL=1000: W1 start/clear_done/clear_error in bits 0/1/2.
// STATUS=1004: bits 0 busy,1 done,2 error,3 ap_done,4 ap_idle,5 ap_ready.
// CORE_CYCLES=1008, cumulative LOAD_WRITES=100c, RESULT_READS=1010,
// TRANSFER_CYCLES=1014 (first input write through last result-word read).
// Input and result reads/writes while busy are rejected; result is read-only.
// Reset clears control, not BRAM. Load all inputs before every first job.
module mlkem512_basemul_k2_mmio_adapter #(
    parameter [31:0] BASE_ADDR = 32'h5000_1000
) (
    input wire clk, resetn,
    input wire bus_valid, bus_write,
    input wire [31:0] bus_addr, bus_wdata,
    input wire [3:0] bus_wstrb,
    output wire bus_ready,
    output reg bus_rvalid,
    output reg [31:0] bus_rdata,
    output wire accel_busy, accel_done, accel_error,
    output wire [31:0] core_cycles, load_transactions,
    output wire [31:0] store_transactions, total_cycles
);
    wire [31:0] offset = bus_addr - BASE_ADDR;
    wire hit = bus_addr >= BASE_ADDR && offset < 32'h2000;
    wire aligned = offset[1:0] == 0;
    wire input_window = offset < 32'ha00;
    wire result_window = offset >= 32'ha00 && offset < 32'hc00;
    wire register_window = offset >= 32'h1000 && offset <= 32'h1014;
    reg busy, done, error, hls_start;
    reg read_pending, read_good;
    reg [31:0] read_offset;
    reg [31:0] cycles_reg, loads_reg, stores_reg, transfer_reg;
    reg transfer_active;
    wire hls_done, hls_idle, hls_ready;
    assign bus_ready = resetn && hit && !read_pending && !bus_rvalid;
    wire fire = bus_valid && bus_ready;
    wire write_input = fire && bus_write && aligned && input_window && !busy;
    wire read_memory = fire && !bus_write && aligned && !busy &&
                       (input_window || (result_window && done));
    wire good_read = aligned && (register_window ||
                     (!busy && (input_window || (result_window && done))));
    wire good_write = aligned && ((input_window && !busy) || offset == 32'h1000);
    assign accel_busy = busy;
    assign accel_done = done;
    assign accel_error = error;
    assign core_cycles = cycles_reg;
    assign load_transactions = loads_reg;
    assign store_transactions = stores_reg;
    assign total_cycles = transfer_reg;
    wire [7:0] a_0_address0;
    wire a_0_ce0;
    wire [15:0] a_0_q0;
    wire [7:0] a_0_address1;
    wire a_0_ce1;
    wire [15:0] a_0_q1;
    wire [7:0] a_1_address0;
    wire a_1_ce0;
    wire [15:0] a_1_q0;
    wire [7:0] a_1_address1;
    wire a_1_ce1;
    wire [15:0] a_1_q1;
    wire [7:0] b_0_address0;
    wire b_0_ce0;
    wire [15:0] b_0_q0;
    wire [7:0] b_0_address1;
    wire b_0_ce1;
    wire [15:0] b_0_q1;
    wire [7:0] b_1_address0;
    wire b_1_ce0;
    wire [15:0] b_1_q0;
    wire [7:0] b_1_address1;
    wire b_1_ce1;
    wire [15:0] b_1_q1;
    wire [6:0] b_cache_0_address0;
    wire b_cache_0_ce0;
    wire [15:0] b_cache_0_q0;
    wire [6:0] b_cache_1_address0;
    wire b_cache_1_ce0;
    wire [15:0] b_cache_1_q0;
    wire [7:0] result_address0;
    wire result_ce0;
    wire result_we0;
    wire [15:0] result_d0;
    wire [7:0] result_address1;
    wire result_ce1;
    wire result_we1;
    wire [15:0] result_d1;
    mlkem512_basemul_acc_k2 hls_core (
        .ap_clk(clk), .ap_rst(!resetn), .ap_start(hls_start),
        .ap_done(hls_done), .ap_idle(hls_idle), .ap_ready(hls_ready),
        .a_0_address0(a_0_address0), .a_0_ce0(a_0_ce0), .a_0_q0(a_0_q0),
        .a_0_address1(a_0_address1), .a_0_ce1(a_0_ce1), .a_0_q1(a_0_q1),
        .a_1_address0(a_1_address0), .a_1_ce0(a_1_ce0), .a_1_q0(a_1_q0),
        .a_1_address1(a_1_address1), .a_1_ce1(a_1_ce1), .a_1_q1(a_1_q1),
        .b_0_address0(b_0_address0), .b_0_ce0(b_0_ce0), .b_0_q0(b_0_q0),
        .b_0_address1(b_0_address1), .b_0_ce1(b_0_ce1), .b_0_q1(b_0_q1),
        .b_1_address0(b_1_address0), .b_1_ce0(b_1_ce0), .b_1_q0(b_1_q0),
        .b_1_address1(b_1_address1), .b_1_ce1(b_1_ce1), .b_1_q1(b_1_q1),
        .b_cache_0_address0(b_cache_0_address0), .b_cache_0_ce0(b_cache_0_ce0),
        .b_cache_0_q0(b_cache_0_q0),
        .b_cache_1_address0(b_cache_1_address0), .b_cache_1_ce0(b_cache_1_ce0),
        .b_cache_1_q0(b_cache_1_q0),
        .result_address0(result_address0), .result_ce0(result_ce0),
        .result_we0(result_we0), .result_d0(result_d0),
        .result_address1(result_address1), .result_ce1(result_ce1),
        .result_we1(result_we1), .result_d1(result_d1)
    );

    wire [31:0] host_read [0:6];
    wire host_0 = offset >= 32'h0 && offset < 32'h200;
    wire en_host_0 = host_0 && (write_input || read_memory);
    wire [1:0] we_host_0_0 = (host_0 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_0_1 = (host_0 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q0_0, ram_q0_1;
    assign host_read[0] = {ram_q0_1, ram_q0_0};
    assign a_0_q0 = ram_q0_0;
    assign a_0_q1 = ram_q0_1;
    mlkem512_tdp_bram #(.ADDR_BITS(8)) a_0_bram (.clk(clk),
        .en0(busy ? a_0_ce0 : en_host_0),
        .we0(busy ? 2'b0 : we_host_0_0),
        .addr0(busy ? a_0_address0 : {offset[8:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q0_0),
        .en1(busy ? a_0_ce1 : en_host_0),
        .we1(busy ? 2'b0 : we_host_0_1),
        .addr1(busy ? a_0_address1 : {offset[8:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q0_1));
    wire host_1 = offset >= 32'h200 && offset < 32'h400;
    wire en_host_1 = host_1 && (write_input || read_memory);
    wire [1:0] we_host_1_0 = (host_1 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_1_1 = (host_1 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q1_0, ram_q1_1;
    assign host_read[1] = {ram_q1_1, ram_q1_0};
    assign a_1_q0 = ram_q1_0;
    assign a_1_q1 = ram_q1_1;
    mlkem512_tdp_bram #(.ADDR_BITS(8)) a_1_bram (.clk(clk),
        .en0(busy ? a_1_ce0 : en_host_1),
        .we0(busy ? 2'b0 : we_host_1_0),
        .addr0(busy ? a_1_address0 : {offset[8:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q1_0),
        .en1(busy ? a_1_ce1 : en_host_1),
        .we1(busy ? 2'b0 : we_host_1_1),
        .addr1(busy ? a_1_address1 : {offset[8:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q1_1));
    wire host_2 = offset >= 32'h400 && offset < 32'h600;
    wire en_host_2 = host_2 && (write_input || read_memory);
    wire [1:0] we_host_2_0 = (host_2 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_2_1 = (host_2 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q2_0, ram_q2_1;
    assign host_read[2] = {ram_q2_1, ram_q2_0};
    assign b_0_q0 = ram_q2_0;
    assign b_0_q1 = ram_q2_1;
    mlkem512_tdp_bram #(.ADDR_BITS(8)) b_0_bram (.clk(clk),
        .en0(busy ? b_0_ce0 : en_host_2),
        .we0(busy ? 2'b0 : we_host_2_0),
        .addr0(busy ? b_0_address0 : {offset[8:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q2_0),
        .en1(busy ? b_0_ce1 : en_host_2),
        .we1(busy ? 2'b0 : we_host_2_1),
        .addr1(busy ? b_0_address1 : {offset[8:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q2_1));
    wire host_3 = offset >= 32'h600 && offset < 32'h800;
    wire en_host_3 = host_3 && (write_input || read_memory);
    wire [1:0] we_host_3_0 = (host_3 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_3_1 = (host_3 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q3_0, ram_q3_1;
    assign host_read[3] = {ram_q3_1, ram_q3_0};
    assign b_1_q0 = ram_q3_0;
    assign b_1_q1 = ram_q3_1;
    mlkem512_tdp_bram #(.ADDR_BITS(8)) b_1_bram (.clk(clk),
        .en0(busy ? b_1_ce0 : en_host_3),
        .we0(busy ? 2'b0 : we_host_3_0),
        .addr0(busy ? b_1_address0 : {offset[8:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q3_0),
        .en1(busy ? b_1_ce1 : en_host_3),
        .we1(busy ? 2'b0 : we_host_3_1),
        .addr1(busy ? b_1_address1 : {offset[8:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q3_1));
    wire host_4 = offset >= 32'h800 && offset < 32'h900;
    wire en_host_4 = host_4 && (write_input || read_memory);
    wire [1:0] we_host_4_0 = (host_4 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_4_1 = (host_4 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q4_0, ram_q4_1;
    assign host_read[4] = {ram_q4_1, ram_q4_0};
    assign b_cache_0_q0 = ram_q4_0;
    mlkem512_tdp_bram #(.ADDR_BITS(7)) b_cache_0_bram (.clk(clk),
        .en0(busy ? b_cache_0_ce0 : en_host_4),
        .we0(busy ? 2'b0 : we_host_4_0),
        .addr0(busy ? b_cache_0_address0 : {offset[7:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q4_0),
        .en1(busy ? 1'b0 : en_host_4),
        .we1(busy ? 2'b0 : we_host_4_1),
        .addr1(busy ? 7'b0 : {offset[7:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q4_1));
    wire host_5 = offset >= 32'h900 && offset < 32'ha00;
    wire en_host_5 = host_5 && (write_input || read_memory);
    wire [1:0] we_host_5_0 = (host_5 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_5_1 = (host_5 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q5_0, ram_q5_1;
    assign host_read[5] = {ram_q5_1, ram_q5_0};
    assign b_cache_1_q0 = ram_q5_0;
    mlkem512_tdp_bram #(.ADDR_BITS(7)) b_cache_1_bram (.clk(clk),
        .en0(busy ? b_cache_1_ce0 : en_host_5),
        .we0(busy ? 2'b0 : we_host_5_0),
        .addr0(busy ? b_cache_1_address0 : {offset[7:2], 1'b0}),
        .d0(busy ? 16'b0 : bus_wdata[15:0]),
        .q0(ram_q5_0),
        .en1(busy ? 1'b0 : en_host_5),
        .we1(busy ? 2'b0 : we_host_5_1),
        .addr1(busy ? 7'b0 : {offset[7:2], 1'b1}),
        .d1(busy ? 16'b0 : bus_wdata[31:16]),
        .q1(ram_q5_1));
    wire host_6 = offset >= 32'ha00 && offset < 32'hc00;
    wire en_host_6 = host_6 && (write_input || read_memory);
    wire [1:0] we_host_6_0 = (host_6 && write_input) ? bus_wstrb[1:0] : 2'b0;
    wire [1:0] we_host_6_1 = (host_6 && write_input) ? bus_wstrb[3:2] : 2'b0;
    wire [15:0] ram_q6_0, ram_q6_1;
    assign host_read[6] = {ram_q6_1, ram_q6_0};
    mlkem512_tdp_bram #(.ADDR_BITS(8)) result_bram (.clk(clk),
        .en0(busy ? result_ce0 : en_host_6),
        .we0(busy ? {2{result_we0}} : we_host_6_0),
        .addr0(busy ? result_address0 : {offset[8:2], 1'b0}),
        .d0(busy ? result_d0 : bus_wdata[15:0]),
        .q0(ram_q6_0),
        .en1(busy ? result_ce1 : en_host_6),
        .we1(busy ? {2{result_we1}} : we_host_6_1),
        .addr1(busy ? result_address1 : {offset[8:2], 1'b1}),
        .d1(busy ? result_d1 : bus_wdata[31:16]),
        .q1(ram_q6_1));

    reg [31:0] read_data;
    always @* begin
        read_data = 0;
        if (read_good) begin
            if (read_offset < 'h200) read_data = host_read[0];
            else if (read_offset < 'h400) read_data = host_read[1];
            else if (read_offset < 'h600) read_data = host_read[2];
            else if (read_offset < 'h800) read_data = host_read[3];
            else if (read_offset < 'h900) read_data = host_read[4];
            else if (read_offset < 'ha00) read_data = host_read[5];
            else if (read_offset < 'hc00) read_data = host_read[6];
            else case (read_offset)
                'h1004: read_data = {16'h5120,10'b0,hls_ready,hls_idle,hls_done,error,done,busy};
                'h1008: read_data = cycles_reg;
                'h100c: read_data = loads_reg;
                'h1010: read_data = stores_reg;
                'h1014: read_data = transfer_reg;
                default: read_data = 0;
            endcase
        end
    end
    always @(posedge clk) begin
        if (!resetn) begin
            busy <= 0; done <= 0; error <= 0; hls_start <= 0;
            bus_rvalid <= 0; bus_rdata <= 0;
            read_pending <= 0; read_good <= 0; read_offset <= 0;
            cycles_reg <= 0; loads_reg <= 0; stores_reg <= 0;
            transfer_reg <= 0; transfer_active <= 0;
        end else begin
            bus_rvalid <= read_pending;
            read_pending <= 0;
            if (read_pending) bus_rdata <= read_data;
            // Hold start until the last loop input is accepted. Deasserting
            // only at done would inject unwanted tokens for another job.
            if (hls_start && hls_ready) hls_start <= 0;
            if (busy) cycles_reg <= cycles_reg + 1'b1;
            if (busy && hls_done) begin busy <= 0; done <= 1; end
            if (transfer_active) transfer_reg <= transfer_reg + 1'b1;
            if (write_input && |bus_wstrb) begin
                loads_reg <= loads_reg + 1'b1;
                done <= 0;
                if (!transfer_active) begin transfer_active <= 1; transfer_reg <= 1; end
            end
            if (fire && !bus_write) begin
                read_pending <= 1;
                read_good <= good_read;
                read_offset <= offset;
                if (!good_read) error <= 1;
                if (read_memory && result_window) begin
                    stores_reg <= stores_reg + 1'b1;
                    if (offset == 'hbfc) transfer_active <= 0;
                end
            end
            if (fire && bus_write) begin
                if (!good_write) error <= 1;
                else if (offset == 'h1000 && bus_wstrb[0]) begin
                    if (bus_wdata[1]) done <= 0;
                    if (bus_wdata[2]) error <= 0;
                    if (bus_wdata[0]) begin
                        if (busy || !hls_idle) error <= 1;
                        else begin busy <= 1; done <= 0; cycles_reg <= 0; hls_start <= 1; end
                    end
                end
            end
        end
    end
endmodule
