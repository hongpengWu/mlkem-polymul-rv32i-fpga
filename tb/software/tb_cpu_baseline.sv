`timescale 1ns/1ps

// Runs the compiled firmware on the implemented CPU/AXI/XPM RAM subsystem.
// The separately generated oracle uses direct negacyclic convolution; this
// monitor never substitutes data, arithmetic results, or CPU register values.
module tb_cpu_baseline;
  parameter integer CPU_ENABLE_MUL = 0;
  parameter integer CPU_ENABLE_FAST_MUL = 0;
  parameter integer CPU_ENABLE_DIV = 0;
  // May be zero on an M-enabled CPU to test the identical RV32I image.
  parameter integer EXPECT_M = 0;
  parameter integer TIMEOUT_CYCLES = 100000000;

  localparam integer CASES = 8;
  localparam integer N = 256;
  localparam integer Q = 3329;
  localparam integer ORACLE_WORDS = CASES*3*N;
  localparam [31:0] RAM_LIMIT = 32'h00004000;
  localparam [31:0] STACK_BOTTOM = 32'h000037f0;
  localparam [31:0] STACK_TOP = 32'h00003ff0;
  localparam [31:0] DEBUG_BASE = 32'h50000000;
  localparam [31:0] STATUS_RUN = 32'h52554e21;
  localparam [31:0] STATUS_PASS = 32'h600d600d;

  localparam integer WAIT_CASE = 0;
  localparam integer INPUTS = 1;
  localparam integer UNSEGMENTED_RUN = 2;
  localparam integer UNSEGMENTED_OUTPUT = 3;
  localparam integer WAIT_PROFILE = 4;
  localparam integer PROFILE_RUN = 5;
  localparam integer PROFILE_OUTPUT = 6;
  localparam integer WAIT_COMPLETE = 7;

  reg clk = 0;
  reg resetn = 0;
  wire trap;
  wire [31:0] status;
  wire [383:0] profile_words;
  reg [31:0] oracle [0:ORACLE_WORDS-1];
  integer state = WAIT_CASE;
  integer completed_cases = 0;
  integer current_case = -1;
  integer input_count = 0;
  integer output_count = 0;
  integer result_checks = 0;
  integer cycle_count = 0;
  integer m_window = 0;
  integer m_count [0:7];
  integer m_total = 0;
  integer all_m_total = 0;
  integer op, j, vector_file;
  reg stack_monitor_active = 0;
  reg [31:0] minimum_sp = STACK_TOP;
  reg [31:0] window_minimum_sp = STACK_TOP;
  reg [31:0] output_checksum = 32'h811c9dc5;
  reg [31:0] empty_cycles = 0;
  reg [63:0] phase_sum;
  wire [31:0] observed_sp = dut.cpu.picorv32_core.cpuregs[2];
  wire [31:0] observed_insn = dut.cpu.picorv32_core.pcpi_insn;

  always #5 clk = ~clk;

  cpu_benchmark_system #(
    .FIRMWARE_INIT_FILE("cpu_baseline.mem"),
    .RAM_ADDR_BITS(12),
    .CPU_ENABLE_MUL(CPU_ENABLE_MUL),
    .CPU_ENABLE_FAST_MUL(CPU_ENABLE_FAST_MUL),
    .CPU_ENABLE_DIV(CPU_ENABLE_DIV)
  ) dut (
    .clk(clk), .resetn(resetn), .trap(trap),
    .status_out(status), .profile_words(profile_words)
  );

  function automatic valid_address(input [31:0] address);
    valid_address = address < RAM_LIMIT ||
                    address[31:6] == DEBUG_BASE[31:6];
  endfunction

  task automatic require_state(input integer required, input integer event_code);
    begin
      if (state != required)
        $fatal(1, "CPU_BASELINE_FAIL event=%0d state=%0d expected=%0d case=%0d cycle=%0d",
               event_code, state, required, current_case, cycle_count);
      if (dut.debug_regs[2] !== current_case && event_code != 1 && event_code != 15)
        $fatal(1, "CPU_BASELINE_FAIL changed case register: expected=%0d actual=%h",
               current_case, dut.debug_regs[2]);
    end
  endtask

  task automatic open_window(input integer window_number);
    begin
      if (m_window != 0)
        $fatal(1, "CPU_BASELINE_FAIL nested M observation window");
      m_window = window_number;
      m_total = 0;
      for (integer k = 0; k < 8; k = k+1) m_count[k] = 0;
      window_minimum_sp = observed_sp;
    end
  endtask

  task automatic close_window(input integer window_number);
    begin
      if (m_window != window_number)
        $fatal(1, "CPU_BASELINE_FAIL incorrect M window close");
      m_window = 0;
      if (EXPECT_M == 0 && m_total != 0)
        $fatal(1, "CPU_BASELINE_FAIL RV32I firmware executed %0d M instructions", m_total);
      if (EXPECT_M != 0 && (m_total == 0 || m_count[0] == 0))
        $fatal(1, "CPU_BASELINE_FAIL RV32IM algorithm window has no MUL: M=%0d MUL=%0d",
               m_total, m_count[0]);
      output_count = 0;
      output_checksum = 32'h811c9dc5;
    end
  endtask

  task automatic check_output(input integer event_code);
    reg [31:0] payload;
    begin
      if (output_count >= N || dut.debug_regs[12] !== output_count)
        $fatal(1, "CPU_BASELINE_FAIL output index event=%0d case=%0d expected=%0d actual=%h",
               event_code, current_case, output_count, dut.debug_regs[12]);
      payload = dut.debug_regs[13];
      if ((^payload) === 1'bx || payload >= Q)
        $fatal(1, "CPU_BASELINE_FAIL noncanonical output event=%0d case=%0d index=%0d value=%h",
               event_code, current_case, output_count, payload);
      if (payload !== oracle[current_case*3*N+2*N+output_count])
        $fatal(1, "CPU_BASELINE_FAIL result event=%0d case=%0d index=%0d got=%h expected=%h",
               event_code, current_case, output_count, payload,
               oracle[current_case*3*N+2*N+output_count]);
      output_checksum = {output_checksum[26:0],output_checksum[31:27]} ^ payload;
      output_count = output_count+1;
      result_checks = result_checks+1;
    end
  endtask

  task automatic check_metrics(input integer profiled);
    begin
      if (output_count != N)
        $fatal(1, "CPU_BASELINE_FAIL incomplete results case=%0d count=%0d", current_case, output_count);
      if ((^dut.debug_regs[9]) === 1'bx || dut.debug_regs[9] <= empty_cycles)
        $fatal(1, "CPU_BASELINE_FAIL invalid total cycles case=%0d total=%h", current_case, dut.debug_regs[9]);
      if (dut.debug_regs[10] !== empty_cycles || empty_cycles == 0)
        $fatal(1, "CPU_BASELINE_FAIL invalid/changed empty bracket");
      if (dut.debug_regs[11] !== output_checksum)
        $fatal(1, "CPU_BASELINE_FAIL checksum case=%0d got=%h expected=%h",
               current_case, dut.debug_regs[11], output_checksum);
      if (profiled != 0) begin
        phase_sum = 0;
        for (integer k = 3; k <= 8; k = k+1) begin
          if ((^dut.debug_regs[k]) === 1'bx || dut.debug_regs[k] == 0)
            $fatal(1, "CPU_BASELINE_FAIL missing phase cycles register=%0d", k);
          phase_sum = phase_sum+{32'b0,dut.debug_regs[k]};
        end
        if (phase_sum !== {32'b0,dut.debug_regs[9]})
          $fatal(1, "CPU_BASELINE_FAIL phase sum=%0d total=%0d", phase_sum, dut.debug_regs[9]);
        $display("CPU_BENCH_ROW,%0d,profiled,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0x%08h,0x%08h",
                 current_case, CPU_ENABLE_MUL, CPU_ENABLE_FAST_MUL, CPU_ENABLE_DIV, EXPECT_M,
                 dut.debug_regs[3], dut.debug_regs[4], dut.debug_regs[5],
                 dut.debug_regs[6], dut.debug_regs[7], dut.debug_regs[8],
                 dut.debug_regs[9], empty_cycles, m_total,
                 m_count[0], m_count[1], m_count[2], m_count[3],
                 m_count[4], m_count[5], m_count[6], m_count[7],
                 window_minimum_sp, output_checksum);
      end else begin
        // -1 identifies phases not sampled during the unsegmented run.
        $display("CPU_BENCH_ROW,%0d,unsegmented,%0d,%0d,%0d,%0d,-1,-1,-1,-1,-1,-1,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0x%08h,0x%08h",
                 current_case, CPU_ENABLE_MUL, CPU_ENABLE_FAST_MUL, CPU_ENABLE_DIV, EXPECT_M,
                 dut.debug_regs[9], empty_cycles, m_total,
                 m_count[0], m_count[1], m_count[2], m_count[3],
                 m_count[4], m_count[5], m_count[6], m_count[7],
                 window_minimum_sp, output_checksum);
      end
    end
  endtask

  initial begin
    if ((EXPECT_M != 0 && EXPECT_M != 1) ||
        (EXPECT_M != 0 && !(CPU_ENABLE_MUL || CPU_ENABLE_FAST_MUL)))
      $fatal(1, "CPU_BASELINE_FAIL invalid CPU/firmware expectation parameters");
    for (j = 0; j < ORACLE_WORDS; j = j+1) oracle[j] = 32'hxxxxxxxx;
    for (j = 0; j < 8; j = j+1) m_count[j] = 0;
    vector_file = $fopen("cpu_polymul_vectors.mem", "r");
    if (vector_file == 0) $fatal(1, "CPU_BASELINE_FAIL cannot open independent oracle");
    $fclose(vector_file);
    $readmemh("cpu_polymul_vectors.mem", oracle);
    for (j = 0; j < ORACLE_WORDS; j = j+1)
      if ((^oracle[j]) === 1'bx || oracle[j] >= Q)
        $fatal(1, "CPU_BASELINE_FAIL invalid/missing oracle word %0d", j);
    $display("CPU_BENCH_HEADER,case,mode,cpu_mul,cpu_fast_mul,cpu_div,expect_m,prepare,ntt_a,ntt_b,basemul,invntt,canonical,total,empty,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp,checksum");
    $display("CPU_BASELINE_START ram_bytes=16384 clock_mhz=100 mul=%0d fast_mul=%0d div=%0d expect_m=%0d",
             CPU_ENABLE_MUL, CPU_ENABLE_FAST_MUL, CPU_ENABLE_DIV, EXPECT_M);
    repeat (32) @(negedge clk);
    resetn = 1;
  end

  always @(posedge clk) begin
    if (resetn) begin
      cycle_count = cycle_count+1;
      if (cycle_count >= TIMEOUT_CYCLES)
        $fatal(1, "CPU_BASELINE_FAIL timeout cycle=%0d case=%0d state=%0d status=%h sp=%h",
               cycle_count, current_case, state, status, observed_sp);
      if (trap === 1'b1)
        $fatal(1, "CPU_BASELINE_FAIL CPU trapped cycle=%0d case=%0d pc=%h",
               cycle_count, current_case, dut.cpu.picorv32_core.reg_pc);
      if (status[31:16] === 16'hdead)
        $fatal(1, "CPU_BASELINE_FAIL firmware status=%h detail=%h", status, dut.debug_regs[1]);

      // Watch requests, not just accepted accesses: invalid targets stall AXI.
      if (dut.c_arvalid === 1'b1 && valid_address(dut.c_araddr) !== 1'b1)
        $fatal(1, "CPU_BASELINE_FAIL out-of-map read %h", dut.c_araddr);
      if (dut.c_awvalid === 1'b1 && valid_address(dut.c_awaddr) !== 1'b1)
        $fatal(1, "CPU_BASELINE_FAIL out-of-map write %h", dut.c_awaddr);

      // The startup 'la sp' contains an intermediate AUIPC value. Arm once
      // firmware reports RUN, after startup and the main function prologue.
      // This avoids treating reset zeros or address construction as stack use.
      if (status === STATUS_RUN) stack_monitor_active = 1;
      if (stack_monitor_active) begin
        if ((^observed_sp) === 1'bx || observed_sp < STACK_BOTTOM || observed_sp > STACK_TOP)
          $fatal(1, "CPU_BASELINE_FAIL stack outside reservation sp=%h case=%0d cycle=%0d",
                 observed_sp, current_case, cycle_count);
        if (observed_sp < minimum_sp) minimum_sp = observed_sp;
        if (m_window != 0 && observed_sp < window_minimum_sp)
          window_minimum_sp = observed_sp;
      end

      if (m_window != 0 && dut.cpu.picorv32_core.pcpi_valid &&
          dut.cpu.picorv32_core.pcpi_int_ready) begin
        if (observed_insn[31:25] !== 7'b0000001 || observed_insn[6:0] !== 7'b0110011 ||
            (^observed_insn[14:12]) === 1'bx)
          $fatal(1, "CPU_BASELINE_FAIL unexpected PCPI instruction %h", observed_insn);
        op = observed_insn[14:12];
        m_count[op] = m_count[op]+1;
        m_total = m_total+1;
        all_m_total = all_m_total+1;
      end

      // The argument registers were committed before this event write. Read
      // their pre-edge values directly; no delayed sampling or forced state.
      if (dut.local_write_commit && dut.commit_addr == DEBUG_BASE+60) begin
        if (dut.commit_strb !== 4'b1111)
          $fatal(1, "CPU_BASELINE_FAIL partial event write");
        case (dut.commit_data)
          1: begin
            require_state(WAIT_CASE, 1);
            if (completed_cases >= CASES || dut.debug_regs[2] !== completed_cases || status !== STATUS_RUN)
              $fatal(1, "CPU_BASELINE_FAIL invalid case begin expected=%0d actual=%h status=%h",
                     completed_cases, dut.debug_regs[2], status);
            if (!stack_monitor_active) $fatal(1, "CPU_BASELINE_FAIL stack monitor not initialized");
            current_case = completed_cases;
            input_count = 0;
            if (current_case == 0) empty_cycles = dut.debug_regs[10];
            if (empty_cycles == 0 || dut.debug_regs[10] !== empty_cycles)
              $fatal(1, "CPU_BASELINE_FAIL invalid empty bracket at case start");
            state = INPUTS;
            $display("CPU_BASELINE_PROGRESS begin_case=%0d cycle=%0d", current_case, cycle_count);
          end
          2: begin
            require_state(INPUTS, 2);
            if (input_count >= N || dut.debug_regs[12] !== input_count)
              $fatal(1, "CPU_BASELINE_FAIL input index case=%0d expected=%0d actual=%h",
                     current_case, input_count, dut.debug_regs[12]);
            if (dut.debug_regs[13] !== {oracle[current_case*3*N+N+input_count][15:0],
                                       oracle[current_case*3*N+input_count][15:0]})
              $fatal(1, "CPU_BASELINE_FAIL input mismatch case=%0d index=%0d payload=%h",
                     current_case, input_count, dut.debug_regs[13]);
            input_count = input_count+1;
          end
          8: begin
            require_state(INPUTS, 8);
            if (input_count != N) $fatal(1, "CPU_BASELINE_FAIL missing input coefficients");
            open_window(1);
            state = UNSEGMENTED_RUN;
          end
          9: begin
            require_state(UNSEGMENTED_RUN, 9);
            close_window(1);
            state = UNSEGMENTED_OUTPUT;
          end
          3: begin
            require_state(UNSEGMENTED_OUTPUT, 3);
            check_output(3);
          end
          4: begin
            require_state(UNSEGMENTED_OUTPUT, 4);
            check_metrics(0);
            state = WAIT_PROFILE;
          end
          10: begin
            require_state(WAIT_PROFILE, 10);
            open_window(2);
            state = PROFILE_RUN;
          end
          11: begin
            require_state(PROFILE_RUN, 11);
            close_window(2);
            state = PROFILE_OUTPUT;
          end
          5: begin
            require_state(PROFILE_OUTPUT, 5);
            check_output(5);
          end
          6: begin
            require_state(PROFILE_OUTPUT, 6);
            check_metrics(1);
            state = WAIT_COMPLETE;
          end
          7: begin
            require_state(WAIT_COMPLETE, 7);
            completed_cases = completed_cases+1;
            state = WAIT_CASE;
            $display("CPU_BASELINE_PROGRESS complete_case=%0d cycle=%0d checks=%0d min_sp=0x%08h",
                     current_case, cycle_count, result_checks, minimum_sp);
          end
          15: begin
            require_state(WAIT_CASE, 15);
            if (completed_cases != CASES || result_checks != 2*CASES*N ||
                m_window != 0 || status !== STATUS_PASS || !stack_monitor_active)
              $fatal(1, "CPU_BASELINE_FAIL premature completion cases=%0d checks=%0d status=%h",
                     completed_cases, result_checks, status);
            $display("CPU_BASELINE_PASS cases=8 checks=4096 mul=%0d fast_mul=%0d div=%0d expect_m=%0d cycles=%0d m_total=%0d min_sp=0x%08h stack_used=%0d",
                     CPU_ENABLE_MUL, CPU_ENABLE_FAST_MUL, CPU_ENABLE_DIV, EXPECT_M,
                     cycle_count, all_m_total, minimum_sp, STACK_TOP-minimum_sp);
            $finish;
          end
          default: $fatal(1, "CPU_BASELINE_FAIL unknown event %h", dut.commit_data);
        endcase
      end
    end
  end
endmodule
