`timescale 1ns/1ps

// Passive official-vector monitor around the real CPU/AXI/XPM subsystem.
// Expected keys exist only in simulator fixtures, never in CPU firmware/RAM.
module tb_mlkem_keygen;
  parameter integer CPU_ENABLE_MUL = 0;
  parameter integer CPU_ENABLE_FAST_MUL = 0;
  parameter integer CPU_ENABLE_DIV = 0;
  parameter integer EXPECT_M = 0;
  parameter integer TIMEOUT_CYCLES = 100000000;

  localparam integer MAX_CASES = 100;
  localparam integer INPUT_CASE_WORDS = 17;
  localparam integer EXPECTED_CASE_WORDS = 609;
  localparam integer INPUT_WORDS = 8+MAX_CASES*INPUT_CASE_WORDS;
  localparam integer EXPECTED_WORDS = 8+MAX_CASES*EXPECTED_CASE_WORDS;
  localparam [31:0] RAM_LIMIT = 32'h00010000;
  localparam [31:0] STACK_BOTTOM = 32'h0000bff0;
  localparam [31:0] STACK_TOP = 32'h0000fff0;
  localparam [31:0] DEBUG_BASE = 32'h50000000;
  localparam [31:0] STATUS_RUN = 32'h4b415452;
  localparam [31:0] STATUS_PASS = 32'h4b415450;
  localparam [31:0] STATUS_FAIL = 32'h4b415446;
  localparam integer WAIT_CASE=0, INPUT_D=1, INPUT_Z=2, WAIT_MEASURE=3;
  localparam integer MEASURE=4, OUTPUT_EK=5, OUTPUT_DK=6, WAIT_END=7;

  reg clk=0, resetn=0;
  wire trap;
  wire [31:0] status;
  wire [383:0] profile_words;
  reg [31:0] input_fixture[0:INPUT_WORDS-1];
  reg [31:0] expected_fixture[0:EXPECTED_WORDS-1];
  integer fixture_cases=0, input_words_read=0, expected_words_read=0;
  integer state=WAIT_CASE, completed_cases=0, current_case=-1;
  integer cycle_count=0, stream_words=0, input_checks=0, output_checks=0;
  integer case_input_checks=0, case_output_checks=0;
  integer rdcycle_samples=0, calibration_samples=0;
  integer m_count[0:7], all_m_count[0:7];
  integer m_total=0, all_m_total=0;
  integer vector_file, scan_result, j, op;
  reg [31:0] file_word, current_tcid;
  reg [31:0] calibration_start, observed_empty, empty_cycles;
  reg [31:0] algorithm_start, algorithm_stop, algorithm_cycles;
  reg [31:0] minimum_sp=STACK_TOP, algorithm_minimum_sp=STACK_TOP;
  reg stack_monitor_active=0, algorithm_active=0;
  wire [31:0] observed_sp=dut.cpu.picorv32_core.cpuregs[2];
  wire [31:0] observed_insn=dut.cpu.picorv32_core.pcpi_insn;
  // This is the exact edge on which PicoRV32 samples count_cycle into reg_out.
  // Checking the CPU state avoids counting the latched decoder flag repeatedly.
  wire rdcycle_executing=(dut.cpu.picorv32_core.cpu_state == 8'b00100000) &&
                         dut.cpu.picorv32_core.instr_rdcycle;

  always #5 clk=~clk;
  cpu_benchmark_system #(
    .FIRMWARE_INIT_FILE("mlkem_keygen.mem"), .RAM_ADDR_BITS(14),
    .CPU_ENABLE_MUL(CPU_ENABLE_MUL), .CPU_ENABLE_FAST_MUL(CPU_ENABLE_FAST_MUL),
    .CPU_ENABLE_DIV(CPU_ENABLE_DIV)
  ) dut(.clk(clk),.resetn(resetn),.trap(trap),
        .status_out(status),.profile_words(profile_words));

  function automatic valid_address(input [31:0] address);
    valid_address=address<RAM_LIMIT || address[31:6]==DEBUG_BASE[31:6];
  endfunction

  task automatic require_state(input integer wanted, input integer event_code);
    begin
      if (state!=wanted)
        $fatal(1,"MLKEM_KEYGEN_FAIL event=%h state=%0d expected=%0d tcId=%0d cycle=%0d",
               event_code,state,wanted,current_tcid,cycle_count);
      if (event_code!=32'h100 && event_code!=32'h1ff &&
          dut.debug_regs[2]!==current_tcid)
        $fatal(1,"MLKEM_KEYGEN_FAIL tcId changed during case");
      if (event_code!=32'h1ff && status!==STATUS_RUN)
        $fatal(1,"MLKEM_KEYGEN_FAIL event without RUN status=%h",status);
      if (dut.debug_regs[1]!==0)
        $fatal(1,"MLKEM_KEYGEN_FAIL firmware error=%h",dut.debug_regs[1]);
    end
  endtask

  task automatic require_empty_record;
    begin
      if (dut.debug_regs[12]!==0 || dut.debug_regs[13]!==0 || dut.debug_regs[14]!==0)
        $fatal(1,"MLKEM_KEYGEN_FAIL nonempty begin/end record");
    end
  endtask

  task automatic check_stream(input integer event_code, input integer words,
                              input integer fixture_offset, input integer is_output);
    reg [31:0] payload, wanted;
    integer b;
    begin
      if (stream_words>=words || dut.debug_regs[12]!==stream_words ||
          dut.debug_regs[14]!==4)
        $fatal(1,"MLKEM_KEYGEN_FAIL stream shape event=%h word=%0d index=%h valid=%h",
               event_code,stream_words,dut.debug_regs[12],dut.debug_regs[14]);
      payload=dut.debug_regs[13];
      wanted=is_output ? expected_fixture[fixture_offset+stream_words] :
                         input_fixture[fixture_offset+stream_words];
      for (b=0;b<4;b=b+1) begin
        if (payload[8*b+:8]!==wanted[8*b+:8])
          $fatal(1,"MLKEM_KEYGEN_FAIL byte mismatch tcId=%0d event=%h byte=%0d got=%h expected=%h",
                 current_tcid,event_code,4*stream_words+b,payload[8*b+:8],wanted[8*b+:8]);
        if (is_output) begin output_checks=output_checks+1; case_output_checks=case_output_checks+1; end
        else begin input_checks=input_checks+1; case_input_checks=case_input_checks+1; end
      end
      stream_words=stream_words+1;
    end
  endtask

  task automatic check_metrics;
    begin
      if (rdcycle_samples!=2 || algorithm_active || algorithm_cycles<=empty_cycles ||
          dut.debug_regs[3]!==algorithm_cycles || dut.debug_regs[8]!==empty_cycles)
        $fatal(1,"MLKEM_KEYGEN_FAIL cycle boundary samples=%0d firmware=%h observed=%0d empty=%0d",
               rdcycle_samples,dut.debug_regs[3],algorithm_cycles,empty_cycles);
      if (dut.debug_regs[9]!==0)
        $fatal(1,"MLKEM_KEYGEN_FAIL nonzero API return=%h",dut.debug_regs[9]);
      if ((EXPECT_M==0 && m_total!=0) || (EXPECT_M==1 && m_count[0]==0))
        $fatal(1,"MLKEM_KEYGEN_FAIL unexpected M execution expect=%0d total=%0d mul=%0d",
               EXPECT_M,m_total,m_count[0]);
    end
  endtask

  initial begin
    if ((EXPECT_M!=0 && EXPECT_M!=1) ||
        (EXPECT_M==1 && (!(CPU_ENABLE_MUL || CPU_ENABLE_FAST_MUL) || !CPU_ENABLE_DIV)))
      $fatal(1,"MLKEM_KEYGEN_FAIL invalid CPU/firmware configuration");
    for (j=0;j<8;j=j+1) begin m_count[j]=0; all_m_count[j]=0; end
    vector_file=$fopen("mlkem512_keygen_input.mem","r");
    if (!vector_file) $fatal(1,"MLKEM_KEYGEN_FAIL missing input fixture");
    while (!$feof(vector_file)) begin
      scan_result=$fscanf(vector_file,"%h",file_word);
      if (scan_result==1) begin
        if (input_words_read>=INPUT_WORDS || (^file_word)===1'bx)
          $fatal(1,"MLKEM_KEYGEN_FAIL oversized/unknown input fixture");
        input_fixture[input_words_read]=file_word; input_words_read=input_words_read+1;
      end else if (!$feof(vector_file)) $fatal(1,"MLKEM_KEYGEN_FAIL malformed input fixture");
    end
    $fclose(vector_file);
    vector_file=$fopen("mlkem512_keygen_expected.mem","r");
    if (!vector_file) $fatal(1,"MLKEM_KEYGEN_FAIL missing expected fixture");
    while (!$feof(vector_file)) begin
      scan_result=$fscanf(vector_file,"%h",file_word);
      if (scan_result==1) begin
        if (expected_words_read>=EXPECTED_WORDS || (^file_word)===1'bx)
          $fatal(1,"MLKEM_KEYGEN_FAIL oversized/unknown expected fixture");
        expected_fixture[expected_words_read]=file_word; expected_words_read=expected_words_read+1;
      end else if (!$feof(vector_file)) $fatal(1,"MLKEM_KEYGEN_FAIL malformed expected fixture");
    end
    $fclose(vector_file);
    if (input_words_read<8 || expected_words_read<8)
      $fatal(1,"MLKEM_KEYGEN_FAIL truncated fixture header");
    fixture_cases=input_fixture[4];
    if (fixture_cases<1 || fixture_cases>MAX_CASES ||
        input_words_read!=8+fixture_cases*INPUT_CASE_WORDS ||
        expected_words_read!=8+fixture_cases*EXPECTED_CASE_WORDS)
      $fatal(1,"MLKEM_KEYGEN_FAIL fixture count/size mismatch");
    for (j=0;j<5;j=j+1)
      if (input_fixture[j]!==expected_fixture[j])
        $fatal(1,"MLKEM_KEYGEN_FAIL input/expected header mismatch word=%0d",j);
    if (input_fixture[0]!==32'h3141544b || input_fixture[1]!==1 ||
        input_fixture[2]!==1 || input_fixture[3]!==512 || input_fixture[5]!==32 ||
        input_fixture[6]!==32 || input_fixture[7]!==0 || expected_fixture[5]!==800 ||
        expected_fixture[6]!==1632 || expected_fixture[7]!==0)
      $fatal(1,"MLKEM_KEYGEN_FAIL invalid fixture metadata");
    for (j=0;j<fixture_cases;j=j+1) begin
      if (input_fixture[8+j*INPUT_CASE_WORDS]!==expected_fixture[8+j*EXPECTED_CASE_WORDS] ||
          (j>0 && input_fixture[8+j*INPUT_CASE_WORDS]<=input_fixture[8+(j-1)*INPUT_CASE_WORDS]))
        $fatal(1,"MLKEM_KEYGEN_FAIL mismatched/duplicate/unordered fixture tcId");
    end
    $display("MLKEM_KEYGEN_HEADER,tcId,param,cpu_mul,cpu_fast_mul,cpu_div,expect_m,raw_cycles,empty_cycles,input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp");
    $display("MLKEM_KEYGEN_START cases=%0d ram_bytes=65536 stack_bytes=16384 clock_mhz=100 mul=%0d fast_mul=%0d div=%0d expect_m=%0d",
             fixture_cases,CPU_ENABLE_MUL,CPU_ENABLE_FAST_MUL,CPU_ENABLE_DIV,EXPECT_M);
    repeat (32) @(negedge clk);
    resetn=1;
  end

  always @(posedge clk) begin
    if (resetn) begin
      cycle_count=cycle_count+1;
      if (cycle_count>=TIMEOUT_CYCLES)
        $fatal(1,"MLKEM_KEYGEN_FAIL timeout cycle=%0d tcId=%0d state=%0d pc=%h sp=%h",
               cycle_count,current_tcid,state,dut.cpu.picorv32_core.reg_pc,observed_sp);
      if (cycle_count%1000000==0)
        $display("MLKEM_KEYGEN_PROGRESS cycle=%0d tcId=%0d state=%0d m_total=%0d sp=%h",
                 cycle_count,current_tcid,state,m_total,observed_sp);
      if (trap!==1'b0) $fatal(1,"MLKEM_KEYGEN_FAIL CPU trap/unknown trap=%b pc=%h",trap,dut.cpu.picorv32_core.reg_pc);
      if (status===STATUS_FAIL) $fatal(1,"MLKEM_KEYGEN_FAIL firmware error=%h",dut.debug_regs[1]);
      if (dut.c_arvalid===1'b1 && valid_address(dut.c_araddr)!==1'b1)
        $fatal(1,"MLKEM_KEYGEN_FAIL out-of-map read %h",dut.c_araddr);
      if (dut.c_awvalid===1'b1 && valid_address(dut.c_awaddr)!==1'b1)
        $fatal(1,"MLKEM_KEYGEN_FAIL out-of-map write %h",dut.c_awaddr);
      // Arm after startup constructs SP; subsequently monitor every CPU cycle.
      if (status===STATUS_RUN) stack_monitor_active=1;
      if (stack_monitor_active) begin
        if ((^observed_sp)===1'bx || observed_sp<STACK_BOTTOM || observed_sp>STACK_TOP || observed_sp[3:0]!=0)
          $fatal(1,"MLKEM_KEYGEN_FAIL invalid stack pointer %h tcId=%0d",observed_sp,current_tcid);
        if (observed_sp<minimum_sp) minimum_sp=observed_sp;
        if (algorithm_active && observed_sp<algorithm_minimum_sp) algorithm_minimum_sp=observed_sp;
      end

      if (rdcycle_executing) begin
        if (state==MEASURE) begin
          if (rdcycle_samples==0) begin
            algorithm_start=dut.cpu.picorv32_core.count_cycle[31:0];
            algorithm_active=1; algorithm_minimum_sp=observed_sp;
          end else if (rdcycle_samples==1) begin
            algorithm_stop=dut.cpu.picorv32_core.count_cycle[31:0];
            algorithm_cycles=algorithm_stop-algorithm_start; algorithm_active=0;
          end else $fatal(1,"MLKEM_KEYGEN_FAIL extra rdcycle in algorithm");
          rdcycle_samples=rdcycle_samples+1;
        end else if (state==WAIT_CASE && completed_cases==0 && calibration_samples<2) begin
          if (calibration_samples==0) calibration_start=dut.cpu.picorv32_core.count_cycle[31:0];
          else observed_empty=dut.cpu.picorv32_core.count_cycle[31:0]-calibration_start;
          calibration_samples=calibration_samples+1;
        end else $fatal(1,"MLKEM_KEYGEN_FAIL rdcycle outside declared measurement window");
      end

      if (dut.cpu.picorv32_core.pcpi_valid && dut.cpu.picorv32_core.pcpi_int_ready) begin
        if (observed_insn[31:25]!==7'b0000001 || observed_insn[6:0]!==7'b0110011 ||
            (^observed_insn[14:12])===1'bx)
          $fatal(1,"MLKEM_KEYGEN_FAIL unexpected completed PCPI instruction %h",observed_insn);
        op=observed_insn[14:12]; all_m_count[op]=all_m_count[op]+1; all_m_total=all_m_total+1;
        if (EXPECT_M==0) $fatal(1,"MLKEM_KEYGEN_FAIL RV32I image executed M instruction");
        if (algorithm_active) begin m_count[op]=m_count[op]+1; m_total=m_total+1; end
      end

      if (dut.local_write_commit && dut.commit_addr[31:6]==DEBUG_BASE[31:6]) begin
        if (dut.commit_strb!==4'b1111 || dut.commit_addr[1:0]!==0)
          $fatal(1,"MLKEM_KEYGEN_FAIL partial/unaligned debug write");
        if (algorithm_active)
          $fatal(1,"MLKEM_KEYGEN_FAIL debug write inside timed algorithm");
        if (dut.commit_addr==DEBUG_BASE+60) begin
          case (dut.commit_data)
            32'h100: begin
              require_state(WAIT_CASE,32'h100); require_empty_record();
              if (completed_cases>=fixture_cases || !stack_monitor_active || calibration_samples!=2 ||
                  dut.debug_regs[2]!==input_fixture[8+completed_cases*INPUT_CASE_WORDS] ||
                  dut.debug_regs[4]!==512 || dut.debug_regs[5]!==800 ||
                  dut.debug_regs[6]!==1632 || dut.debug_regs[7]!==fixture_cases ||
                  dut.debug_regs[8]!==observed_empty || observed_empty==0)
                $fatal(1,"MLKEM_KEYGEN_FAIL invalid case metadata/calibration");
              current_case=completed_cases; current_tcid=dut.debug_regs[2];
              empty_cycles=dut.debug_regs[8]; case_input_checks=0; case_output_checks=0;
              stream_words=0; rdcycle_samples=0; m_total=0;
              for (j=0;j<8;j=j+1) m_count[j]=0;
              state=INPUT_D;
              $display("MLKEM_KEYGEN_PROGRESS begin_tcId=%0d cycle=%0d",current_tcid,cycle_count);
            end
            32'h101: begin
              require_state(INPUT_D,32'h101);
              check_stream(32'h101,8,9+current_case*INPUT_CASE_WORDS,0);
              if (stream_words==8) begin stream_words=0; state=INPUT_Z; end
            end
            32'h102: begin
              require_state(INPUT_Z,32'h102);
              check_stream(32'h102,8,17+current_case*INPUT_CASE_WORDS,0);
              if (stream_words==8) begin stream_words=0; state=WAIT_MEASURE; end
            end
            32'h108: begin
              require_state(WAIT_MEASURE,32'h108);
              if (case_input_checks!=64 || rdcycle_samples!=0 || algorithm_active)
                $fatal(1,"MLKEM_KEYGEN_FAIL premature/nested measurement");
              state=MEASURE;
            end
            32'h109: begin
              require_state(MEASURE,32'h109);
              if (rdcycle_samples!=2 || algorithm_active || algorithm_cycles<=empty_cycles)
                $fatal(1,"MLKEM_KEYGEN_FAIL missing/invalid algorithm rdcycle pair");
              state=OUTPUT_EK;
            end
            32'h103: begin
              require_state(OUTPUT_EK,32'h103); check_metrics();
              check_stream(32'h103,200,9+current_case*EXPECTED_CASE_WORDS,1);
              if (stream_words==200) begin stream_words=0; state=OUTPUT_DK; end
            end
            32'h104: begin
              require_state(OUTPUT_DK,32'h104); check_metrics();
              check_stream(32'h104,408,209+current_case*EXPECTED_CASE_WORDS,1);
              if (stream_words==408) begin stream_words=0; state=WAIT_END; end
            end
            32'h105: begin
              require_state(WAIT_END,32'h105); require_empty_record(); check_metrics();
              if (case_input_checks!=64 || case_output_checks!=2432)
                $fatal(1,"MLKEM_KEYGEN_FAIL incomplete case bytes");
              $display("MLKEM_KEYGEN_ROW,%0d,512,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0x%08h",
                       current_tcid,CPU_ENABLE_MUL,CPU_ENABLE_FAST_MUL,CPU_ENABLE_DIV,EXPECT_M,
                       algorithm_cycles,empty_cycles,case_input_checks,case_output_checks,m_total,
                       m_count[0],m_count[1],m_count[2],m_count[3],m_count[4],m_count[5],m_count[6],m_count[7],algorithm_minimum_sp);
              completed_cases=completed_cases+1; state=WAIT_CASE;
            end
            32'h1ff: begin
              require_state(WAIT_CASE,32'h1ff);
              if (completed_cases!=fixture_cases || input_checks!=64*fixture_cases ||
                  output_checks!=2432*fixture_cases || status!==STATUS_PASS || algorithm_active)
                $fatal(1,"MLKEM_KEYGEN_FAIL premature completion cases=%0d inputs=%0d outputs=%0d status=%h",
                       completed_cases,input_checks,output_checks,status);
              $display("MLKEM_KEYGEN_PASS cases=%0d input_bytes=%0d output_bytes=%0d cpu_mul=%0d cpu_fast_mul=%0d cpu_div=%0d expect_m=%0d cycles=%0d all_m=%0d min_sp=0x%08h stack_used=%0d",
                       completed_cases,input_checks,output_checks,CPU_ENABLE_MUL,CPU_ENABLE_FAST_MUL,
                       CPU_ENABLE_DIV,EXPECT_M,cycle_count,all_m_total,minimum_sp,STACK_TOP-minimum_sp);
              $finish;
            end
            default: $fatal(1,"MLKEM_KEYGEN_FAIL unknown event=%h",dut.commit_data);
          endcase
        end
      end
    end
  end
endmodule
