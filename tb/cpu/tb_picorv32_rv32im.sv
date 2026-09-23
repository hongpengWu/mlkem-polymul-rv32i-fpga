`timescale 1ns/1ps

// Standalone ISA validation, not a board/application performance benchmark.
// The real PicoRV32 fetches an instruction stream assembled below. Native
// memory acknowledges at the first rising edge for which mem_valid is high.
// No CPU registers, decoder state or arithmetic results are forced.
module tb_picorv32_rv32im;
  parameter integer FAST_MUL = 0;
  localparam integer CORNERS = 16;
  localparam integer RANDOM_PAIRS = 256;
  localparam integer PAIRS = CORNERS*CORNERS + RANDOM_PAIRS;
  localparam integer TESTS = PAIRS*8;
  localparam integer ROM_WORDS = 65536;
  localparam [31:0] SEED = 32'h6d6c6b65;
  localparam [31:0] OUTPUT_BASE = 32'h10000000;

  reg clk = 0;
  reg resetn = 0;
  wire trap, mem_valid, mem_instr;
  wire [31:0] mem_addr, mem_wdata;
  wire [3:0] mem_wstrb;
  reg [31:0] rom [0:ROM_WORDS-1];
  wire mem_ready = mem_valid;
  wire [31:0] mem_rdata = mem_addr < ROM_WORDS*4 ? rom[mem_addr >> 2] : 32'b0;
  wire pcpi_valid;
  wire [31:0] pcpi_insn, pcpi_rs1, pcpi_rs2;
  reg [31:0] operand_a [0:TESTS-1];
  reg [31:0] operand_b [0:TESTS-1];
  reg [31:0] expected [0:TESTS-1];
  reg [31:0] corners [0:CORNERS-1];
  reg [31:0] random_state, next_a, next_b;
  integer program_words = 0;
  integer generated_tests = 0;
  integer checked_results = 0;
  integer checked_cycles = 0;
  integer pcpi_completed = 0;
  integer cycle = 0;
  integer empty_bracket_cycles = 0;
  integer raw_min [0:7], raw_max [0:7], raw_sum [0:7], sample_count [0:7];
  integer service_min [0:7], service_max [0:7], service_sum [0:7];
  integer service_start = 0;
  reg service_active = 0;
  integer i, j, op, pair_index, delta, operation;

  always #5 clk = ~clk;

  picorv32 #(
    .ENABLE_COUNTERS(1), .ENABLE_COUNTERS64(0),
    .ENABLE_MUL(1), .ENABLE_FAST_MUL(FAST_MUL), .ENABLE_DIV(1),
    .ENABLE_TRACE(1), .REGS_INIT_ZERO(1), .STACKADDR(32'h00000ff0)
  ) dut (
    .clk(clk), .resetn(resetn), .trap(trap),
    .mem_valid(mem_valid), .mem_instr(mem_instr), .mem_ready(mem_ready),
    .mem_addr(mem_addr), .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb),
    .mem_rdata(mem_rdata),
    .pcpi_valid(pcpi_valid), .pcpi_insn(pcpi_insn),
    .pcpi_rs1(pcpi_rs1), .pcpi_rs2(pcpi_rs2),
    .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
    .irq(32'b0)
  );

  function automatic [31:0] xorshift32(input [31:0] state);
    reg [31:0] value;
    begin
      value = state ^ (state << 13);
      value = value ^ (value >> 17);
      xorshift32 = value ^ (value << 5);
    end
  endfunction

  function automatic string opcode_name(input integer funct3);
    case (funct3)
      0: opcode_name = "MUL";
      1: opcode_name = "MULH";
      2: opcode_name = "MULHSU";
      3: opcode_name = "MULHU";
      4: opcode_name = "DIV";
      5: opcode_name = "DIVU";
      6: opcode_name = "REM";
      7: opcode_name = "REMU";
      default: opcode_name = "INVALID";
    endcase
  endfunction

  // Explicit 64-bit operands avoid host integer width and mixed-sign traps.
  // Division special cases follow the RISC-V M extension, including overflow.
  function automatic [31:0] reference_result(
      input integer funct3, input [31:0] a, input [31:0] b);
    reg signed [63:0] signed_a, signed_b, positive_b, signed_product;
    reg [63:0] unsigned_product;
    begin
      signed_a = {{32{a[31]}}, a};
      signed_b = {{32{b[31]}}, b};
      positive_b = {32'b0, b};
      unsigned_product = {32'b0, a} * {32'b0, b};
      signed_product = signed_a * signed_b;
      case (funct3)
        0: reference_result = unsigned_product[31:0];
        1: reference_result = signed_product[63:32];
        2: begin
          signed_product = signed_a * positive_b;
          reference_result = signed_product[63:32];
        end
        3: reference_result = unsigned_product[63:32];
        4: begin
          if (b == 0) reference_result = 32'hffffffff;
          else if (a == 32'h80000000 && b == 32'hffffffff)
            reference_result = 32'h80000000;
          else reference_result = signed_a / signed_b;
        end
        5: reference_result = b == 0 ? 32'hffffffff : a / b;
        6: begin
          if (b == 0) reference_result = a;
          else if (a == 32'h80000000 && b == 32'hffffffff)
            reference_result = 0;
          else reference_result = signed_a % signed_b;
        end
        7: reference_result = b == 0 ? a : a % b;
        default: reference_result = 32'hxxxxxxxx;
      endcase
    end
  endfunction

  task automatic emit(input [31:0] instruction);
    begin
      if (program_words >= ROM_WORDS) $fatal(1, "Instruction ROM overflow");
      rom[program_words] = instruction;
      program_words = program_words + 1;
    end
  endtask

  task automatic load_constant(input [4:0] rd, input [31:0] value);
    reg [31:0] adjusted;
    begin
      adjusted = value + 32'h00000800;
      emit({adjusted[31:12], rd, 7'b0110111}); // LUI
      emit({value[11:0], rd, 3'b000, rd, 7'b0010011}); // ADDI
    end
  endtask

  task automatic emit_case(input integer funct3, input [31:0] a, input [31:0] b);
    begin
      operand_a[generated_tests] = a;
      operand_b[generated_tests] = b;
      expected[generated_tests] = reference_result(funct3, a, b);
      load_constant(5'd1, a);
      load_constant(5'd2, b);
      emit(32'hc0002273); // RDCYCLE x4
      emit({7'b0000001, 5'd2, 5'd1, funct3[2:0], 5'd3, 7'b0110011});
      emit(32'hc00022f3); // RDCYCLE x5
      emit(32'h40428333); // SUB x6,x5,x4
      emit(32'h00352023); // SW x3,0(x10): arithmetic result
      emit(32'h00652223); // SW x6,4(x10): raw cycle bracket
      generated_tests = generated_tests + 1;
    end
  endtask

  task automatic print_summary;
    integer index;
    begin
      $display("RV32IM_METRIC,configuration,fast_mul,%0d", FAST_MUL);
      $display("RV32IM_METRIC,coverage,corner_pairs,%0d", CORNERS*CORNERS);
      $display("RV32IM_METRIC,coverage,random_pairs,%0d", RANDOM_PAIRS);
      $display("RV32IM_METRIC,coverage,seed,0x%08x", SEED);
      $display("RV32IM_METRIC,timing,empty_rdcycle_bracket,%0d", empty_bracket_cycles);
      $display("RV32IM_CSV,op,samples,raw_min,raw_mean,raw_max,incremental_min,incremental_mean,incremental_max,pcpi_min,pcpi_mean,pcpi_max");
      for (index = 0; index < 8; index = index + 1) begin
        if (sample_count[index] != PAIRS)
          $fatal(1, "Missing samples: op=%0d samples=%0d", index, sample_count[index]);
        $display("RV32IM_CSV,%s,%0d,%0d,%0.3f,%0d,%0d,%0.3f,%0d,%0d,%0.3f,%0d",
          opcode_name(index), sample_count[index], raw_min[index],
          $itor(raw_sum[index])/sample_count[index], raw_max[index],
          raw_min[index]-empty_bracket_cycles,
          $itor(raw_sum[index])/sample_count[index]-empty_bracket_cycles,
          raw_max[index]-empty_bracket_cycles, service_min[index],
          $itor(service_sum[index])/sample_count[index], service_max[index]);
      end
      $display("RV32IM_ISA_PASS tests=%0d pcpi=%0d cycles=%0d fast_mul=%0d",
        checked_results, pcpi_completed, cycle, FAST_MUL);
    end
  endtask

  initial begin
    corners[0] = 32'h00000000; corners[1] = 32'h00000001;
    corners[2] = 32'hffffffff; corners[3] = 32'h80000000;
    corners[4] = 32'h7fffffff; corners[5] = 32'h00000002;
    corners[6] = 32'hfffffffe; corners[7] = 32'h00010000;
    corners[8] = 32'hffff0000; corners[9] = 32'h00000d01;
    corners[10] = 32'hfffff2ff; corners[11] = 32'h55555555;
    corners[12] = 32'haaaaaaaa; corners[13] = 32'h00007fff;
    corners[14] = 32'h00008000; corners[15] = 32'h80000001;
    for (i = 0; i < 8; i = i + 1) begin
      raw_min[i] = 32'h7fffffff; raw_max[i] = 0; raw_sum[i] = 0; sample_count[i] = 0;
      service_min[i] = 32'h7fffffff; service_max[i] = 0; service_sum[i] = 0;
    end
    emit(32'h10000537); // LUI x10,0x10000: test output MMIO base
    // Calibration uses the same RDCYCLE pair and subtraction as every sample.
    emit(32'hc0002273); // RDCYCLE x4
    emit(32'hc00022f3); // RDCYCLE x5
    emit(32'h40428333); // SUB x6,x5,x4
    emit(32'h00652423); // SW x6,8(x10): empty bracket
    for (i = 0; i < CORNERS; i = i + 1)
      for (j = 0; j < CORNERS; j = j + 1)
        for (op = 0; op < 8; op = op + 1)
          emit_case(op, corners[i], corners[j]);
    random_state = SEED;
    for (pair_index = 0; pair_index < RANDOM_PAIRS; pair_index = pair_index + 1) begin
      random_state = xorshift32(random_state); next_a = random_state;
      random_state = xorshift32(random_state); next_b = random_state;
      for (op = 0; op < 8; op = op + 1) emit_case(op, next_a, next_b);
    end
    emit(32'h00052623); // SW x0,12(x10): completion
    emit(32'h0000006f); // JAL x0,0: stop if simulation completion is delayed
    if (generated_tests != TESTS) $fatal(1, "Generated test count mismatch");
    $display("RV32IM_TEST_START tests=%0d program_bytes=%0d seed=0x%08x fast_mul=%0d",
      generated_tests, program_words*4, SEED, FAST_MUL);
    repeat (8) @(negedge clk);
    resetn = 1;
  end

  // Read-only observation of the CPU's internal PCPI completion handshake.
  // Service cycles are edge distance from first pcpi_valid to sampled ready;
  // they exclude instruction decode/fetch and are not CPU instruction latency.
  always @(posedge clk) begin
    if (resetn) begin
      cycle = cycle + 1;
      if (cycle > 2000000) $fatal(1, "RV32IM timeout results=%0d", checked_results);
      if (trap) $fatal(1, "Unexpected CPU trap pc=0x%08x", dut.reg_pc);
      if (pcpi_valid && !service_active) begin
        if (pcpi_completed >= TESTS) $fatal(1, "Unexpected extra PCPI request");
        if (pcpi_rs1 !== operand_a[pcpi_completed] || pcpi_rs2 !== operand_b[pcpi_completed] ||
            pcpi_insn[14:12] !== (pcpi_completed % 8))
          $fatal(1, "Operand/decode mismatch test=%0d instruction=%08x a=%08x b=%08x expected_a=%08x expected_b=%08x",
            pcpi_completed, pcpi_insn, pcpi_rs1, pcpi_rs2,
            operand_a[pcpi_completed], operand_b[pcpi_completed]);
        service_start = cycle;
        service_active = 1;
      end
      if (pcpi_valid && dut.pcpi_int_ready) begin
        if (!service_active) $fatal(1, "Ready without request");
        operation = pcpi_completed % 8;
        delta = cycle - service_start;
        if (delta < service_min[operation]) service_min[operation] = delta;
        if (delta > service_max[operation]) service_max[operation] = delta;
        service_sum[operation] = service_sum[operation] + delta;
        pcpi_completed = pcpi_completed + 1;
        service_active = 0;
      end
      if (mem_valid && mem_ready) begin
        if (mem_instr && (mem_addr[1:0] != 0 || mem_addr >= program_words*4))
          $fatal(1, "Instruction fetch outside generated program: %08x", mem_addr);
        if (mem_wstrb != 0) begin
          if (mem_wstrb != 4'b1111) $fatal(1, "Unexpected partial write");
          case (mem_addr)
            OUTPUT_BASE: begin
              if (checked_results >= TESTS || checked_results != checked_cycles)
                $fatal(1, "Result/cycle ordering error");
              if (mem_wdata !== expected[checked_results])
                $fatal(1, "RV32IM mismatch test=%0d op=%s a=%08x b=%08x expected=%08x actual=%08x",
                  checked_results, opcode_name(checked_results % 8),
                  operand_a[checked_results], operand_b[checked_results],
                  expected[checked_results], mem_wdata);
              checked_results = checked_results + 1;
            end
            OUTPUT_BASE+4: begin
              if (checked_cycles >= TESTS || checked_results != checked_cycles+1)
                $fatal(1, "Cycle/result ordering error");
              if (empty_bracket_cycles <= 0 || mem_wdata <= empty_bracket_cycles || mem_wdata > 1000)
                $fatal(1, "Invalid cycle measurement test=%0d raw=%0d", checked_cycles, mem_wdata);
              operation = checked_cycles % 8;
              if (mem_wdata < raw_min[operation]) raw_min[operation] = mem_wdata;
              if (mem_wdata > raw_max[operation]) raw_max[operation] = mem_wdata;
              raw_sum[operation] = raw_sum[operation] + mem_wdata;
              sample_count[operation] = sample_count[operation] + 1;
              checked_cycles = checked_cycles + 1;
            end
            OUTPUT_BASE+8: begin
              if (empty_bracket_cycles != 0) $fatal(1, "Duplicate calibration");
              empty_bracket_cycles = mem_wdata;
            end
            OUTPUT_BASE+12: begin
              if (checked_results != TESTS || checked_cycles != TESTS || pcpi_completed != TESTS)
                $fatal(1, "Premature completion results=%0d cycles=%0d pcpi=%0d",
                  checked_results, checked_cycles, pcpi_completed);
              print_summary();
              $finish;
            end
            default: $fatal(1, "Unexpected store addr=%08x data=%08x", mem_addr, mem_wdata);
          endcase
        end else if (!mem_instr) $fatal(1, "Unexpected data read addr=%08x", mem_addr);
      end
    end
  end
endmodule
