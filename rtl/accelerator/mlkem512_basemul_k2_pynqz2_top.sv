`timescale 1ns/1ps

// PYNQ-Z2 self-test: load a deterministic nonzero K=2 vector through MMIO,
// run the HLS accelerator, and compare every packed result word through MMIO.
// btn0 restarts the test. LEDs: 0=pass, 1=fail, 2=testing, 3=clock unlocked.
module mlkem512_basemul_k2_pynqz2_top #(
    parameter BIST_MEM_FILE = "basemul_bist.mem"
) (
    input wire sys_clk, input wire btn0, output wire [3:0] led
);
    wire clk100_raw, clk100, feedback_raw, feedback, locked;
    MMCME2_BASE #(.CLKIN1_PERIOD(8.000), .CLKFBOUT_MULT_F(8.000),
        .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.000), .STARTUP_WAIT("FALSE"))
    clock_manager (.CLKIN1(sys_clk), .CLKFBIN(feedback), .RST(1'b0), .PWRDWN(1'b0),
        .CLKFBOUT(feedback_raw), .CLKOUT0(clk100_raw), .LOCKED(locked),
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(),
        .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6());
    BUFG feedback_buffer(.I(feedback_raw),.O(feedback));
    BUFG system_clock_buffer(.I(clk100_raw),.O(clk100));

    wire reset_request = !locked || btn0;
    (* ASYNC_REG = "TRUE" *) reg [3:0] reset_sync = 0;
    always @(posedge clk100 or posedge reset_request)
        if (reset_request) reset_sync <= 0;
        else reset_sync <= {reset_sync[2:0], 1'b1};

    mlkem512_basemul_k2_bist #(.BIST_MEM_FILE(BIST_MEM_FILE)) bist_i (
        .clk(clk100), .resetn(reset_sync[3]),
        .bist_pass(led[0]), .bist_fail(led[1]), .bist_active(led[2])
    );
    assign led[3] = !locked;
endmodule

// The controller and actual adapter are also instantiated by the RTL test.
// ROM layout: 640 input words in ascending MMIO address order, followed by
// 128 expected signed-result words (low coefficient in bits 15:0).
module mlkem512_basemul_k2_bist #(
    parameter BIST_MEM_FILE = "basemul_bist.mem",
    parameter integer TIMEOUT_CYCLES = 1000000
) (
    input wire clk,
    input wire resetn,
    output reg bist_pass,
    output reg bist_fail,
    output wire bist_active
);
    localparam [31:0] BASE_ADDR = 32'h5000_1000;
    localparam [3:0] S_LOAD_ADDR = 0, S_LOAD_WAIT = 1, S_LOAD_WRITE = 2,
        S_START = 3, S_POLL_REQ = 4, S_POLL_WAIT = 5,
        S_EXPECT_ADDR = 6, S_EXPECT_WAIT = 7, S_READ_REQ = 8,
        S_READ_WAIT = 9, S_PASS = 10, S_FAIL = 11;

    reg [3:0] state;
    reg [9:0] word_index;
    reg [31:0] watchdog;
    wire checking_results = state >= S_EXPECT_ADDR && state <= S_READ_WAIT;
    wire [9:0] rom_address = checking_results ? 10'd640 + word_index : word_index;
    (* rom_style = "block" *) reg [31:0] bist_rom [0:767];
    reg [31:0] rom_data;
    initial $readmemh(BIST_MEM_FILE, bist_rom);
    always @(posedge clk) rom_data <= bist_rom[rom_address];

    reg bus_valid, bus_write;
    reg [31:0] bus_addr, bus_wdata;
    reg [3:0] bus_wstrb;
    wire bus_ready, bus_rvalid;
    wire [31:0] bus_rdata;
    wire accel_busy, accel_done, accel_error;
    wire [31:0] core_cycles, load_transactions, store_transactions, total_cycles;

    mlkem512_basemul_k2_mmio_adapter #(.BASE_ADDR(BASE_ADDR)) adapter_i (
        .clk(clk), .resetn(resetn), .bus_valid(bus_valid), .bus_write(bus_write),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_wstrb(bus_wstrb),
        .bus_ready(bus_ready), .bus_rvalid(bus_rvalid), .bus_rdata(bus_rdata),
        .accel_busy(accel_busy), .accel_done(accel_done), .accel_error(accel_error),
        .core_cycles(core_cycles), .load_transactions(load_transactions),
        .store_transactions(store_transactions), .total_cycles(total_cycles)
    );

    assign bist_active = resetn && !bist_pass && !bist_fail;

    always @(*) begin
        bus_valid = 1'b0;
        bus_write = 1'b0;
        bus_addr = BASE_ADDR;
        bus_wdata = 32'b0;
        bus_wstrb = 4'b0;
        case (state)
            S_LOAD_WRITE: begin
                bus_valid = 1'b1;
                bus_write = 1'b1;
                bus_addr = BASE_ADDR + {20'b0, word_index, 2'b00};
                bus_wdata = rom_data;
                bus_wstrb = 4'hf;
            end
            S_START: begin
                bus_valid = 1'b1;
                bus_write = 1'b1;
                bus_addr = BASE_ADDR + 32'h1000;
                bus_wdata = 32'h1;
                bus_wstrb = 4'hf;
            end
            S_POLL_REQ: begin
                bus_valid = 1'b1;
                bus_addr = BASE_ADDR + 32'h1004;
            end
            S_READ_REQ: begin
                bus_valid = 1'b1;
                bus_addr = BASE_ADDR + 32'h0a00 + {20'b0, word_index, 2'b00};
            end
            default: begin end
        endcase
        if (!resetn) bus_valid = 1'b0;
    end

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_LOAD_ADDR;
            word_index <= 0;
            watchdog <= 0;
            bist_pass <= 1'b0;
            bist_fail <= 1'b0;
        end else if (state != S_PASS && state != S_FAIL) begin
            watchdog <= watchdog + 1'b1;
            if (watchdog >= TIMEOUT_CYCLES - 1 || accel_error) begin
                state <= S_FAIL;
                bist_fail <= 1'b1;
            end else begin
                case (state)
                    S_LOAD_ADDR: state <= S_LOAD_WAIT;
                    S_LOAD_WAIT: state <= S_LOAD_WRITE;
                    S_LOAD_WRITE: if (bus_ready) begin
                        if (word_index == 10'd639) state <= S_START;
                        else begin
                            word_index <= word_index + 1'b1;
                            state <= S_LOAD_ADDR;
                        end
                    end
                    S_START: if (bus_ready) state <= S_POLL_REQ;
                    S_POLL_REQ: if (bus_ready) state <= S_POLL_WAIT;
                    S_POLL_WAIT: if (bus_rvalid) begin
                        if (bus_rdata[2]) begin
                            state <= S_FAIL;
                            bist_fail <= 1'b1;
                        end else if (bus_rdata[1] && !bus_rdata[0]) begin
                            word_index <= 0;
                            state <= S_EXPECT_ADDR;
                        end else state <= S_POLL_REQ;
                    end
                    S_EXPECT_ADDR: state <= S_EXPECT_WAIT;
                    S_EXPECT_WAIT: state <= S_READ_REQ;
                    S_READ_REQ: if (bus_ready) state <= S_READ_WAIT;
                    S_READ_WAIT: if (bus_rvalid) begin
                        if (bus_rdata !== rom_data) begin
                            state <= S_FAIL;
                            bist_fail <= 1'b1;
                        end else if (word_index == 10'd127) begin
                            state <= S_PASS;
                            bist_pass <= 1'b1;
                        end else begin
                            word_index <= word_index + 1'b1;
                            state <= S_EXPECT_ADDR;
                        end
                    end
                    default: begin
                        state <= S_FAIL;
                        bist_fail <= 1'b1;
                    end
                endcase
            end
        end
    end
endmodule
