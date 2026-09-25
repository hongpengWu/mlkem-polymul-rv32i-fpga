`timescale 1ns/1ps

// Official inputs enter only through a simulator-host mailbox. Expected outputs
// remain in this testbench; the CPU executes the complete portable algorithm.
module tb_mlkem512_profile;
  parameter integer CPU_ENABLE_MUL=1;
  parameter integer CPU_ENABLE_FAST_MUL=1;
  parameter integer CPU_ENABLE_DIV=1;
  parameter integer EXPECT_M=1;
  parameter integer EXPECTED_CASES=145;
  parameter integer TIMEOUT_CYCLES=100000000;
  parameter integer PROFILE_PHASES=64;

  localparam integer MAX_CASES=145, MAX_WORDS=131072;
  localparam [31:0] RAM_LIMIT=32'h10000, STACK_BOTTOM=32'hbff0, STACK_TOP=32'hfff0;
  localparam [31:0] DEBUG_BASE=32'h50000000;
  localparam [31:0] STATUS_RUN=32'h4b415452, STATUS_PASS=32'h4b415450, STATUS_FAIL=32'h4b415446;
  localparam integer WAIT_CASE=0, ECHO_INPUT=1, WAIT_MEASURE=2, MEASURE=3, OUTPUT_DATA=4, WAIT_END=5;

  reg clk=0, resetn=0;
  wire trap;
  wire [31:0] status;
  wire [383:0] profile_words;
  reg [31:0] input_fixture[0:MAX_WORDS-1], expected_fixture[0:MAX_WORDS-1];
  integer input_offsets[0:MAX_CASES-1], expected_offsets[0:MAX_CASES-1];
  integer input_sizes[0:MAX_CASES-1], output_sizes[0:MAX_CASES-1];
  integer input_words_read=0, expected_words_read=0, fixture_cases=0;
  integer state=WAIT_CASE, completed_cases=0, current_case=-1;
  integer requested_words=0, pending_request=-1;
  integer stream_words=0, input_checks=0, output_checks=0;
  integer case_input_checks=0, case_output_checks=0;
  integer expected_input_bytes=0, expected_output_bytes=0;
  integer rdcycle_samples=0, calibration_samples=0;
  integer m_count[0:7], m_total=0;
  longint unsigned cycle_count=0, case_start_cycle=0, all_m_total=0;
  integer vector_file, scan_result, j, k, pos_in, pos_out, operation;
  integer current_input_offset, current_expected_offset;
  reg [31:0] file_word, empty_cycles, calibration_start, observed_empty;
  reg [31:0] algorithm_start, algorithm_cycles;
  reg [31:0] minimum_sp=STACK_TOP, algorithm_minimum_sp=STACK_TOP;
  reg stack_monitor_active=0, algorithm_active=0;
  // Phase zero owns every measured clock outside a marked scope. A marker
  // changes ownership before this edge is charged: enter belongs to the new
  // scope, exit belongs to its parent. Inclusive duration is exit minus enter.
  localparam integer PROFILE_STACK_LIMIT=32;
  longint unsigned profile_exclusive[0:PROFILE_PHASES-1];
  longint unsigned profile_inclusive[0:PROFILE_PHASES-1];
  longint unsigned profile_calls[0:PROFILE_PHASES-1];
  longint unsigned profile_completed[0:PROFILE_PHASES-1];
  integer profile_stack[0:PROFILE_STACK_LIMIT-1];
  longint unsigned profile_start[0:PROFILE_STACK_LIMIT-1];
  integer profile_depth=0, profile_max_depth=0, profile_owner;
  longint unsigned profile_enters=0, profile_exits=0;
  wire [31:0] observed_sp=dut.cpu.picorv32_core.cpuregs[2];
  wire [31:0] observed_insn=dut.cpu.picorv32_core.pcpi_insn;
  wire rdcycle_executing=(dut.cpu.picorv32_core.cpu_state==8'b00100000) &&
                         dut.cpu.picorv32_core.instr_rdcycle;

  always #5 clk=~clk;
  cpu_benchmark_system #(
    .FIRMWARE_INIT_FILE("mlkem512.mem"), .RAM_ADDR_BITS(14),
    .CPU_ENABLE_MUL(CPU_ENABLE_MUL), .CPU_ENABLE_FAST_MUL(CPU_ENABLE_FAST_MUL),
    .CPU_ENABLE_DIV(CPU_ENABLE_DIV)
  ) dut(.clk(clk),.resetn(resetn),.trap(trap),.status_out(status),.profile_words(profile_words));

  function automatic valid_address(input [31:0] address);
    valid_address=address<RAM_LIMIT || address[31:6]==DEBUG_BASE[31:6];
  endfunction

  task automatic require_state(input integer wanted, input integer event_code);
    begin
      if (state!=wanted)
        $fatal(1,"MLKEM512_FAIL event=%h state=%0d expected=%0d case=%0d cycle=%0d",event_code,state,wanted,current_case,cycle_count);
      if (event_code!=32'h1ff && status!==STATUS_RUN)
        $fatal(1,"MLKEM512_FAIL event without RUN status=%h",status);
      if (dut.debug_regs[1]!==0)
        $fatal(1,"MLKEM512_FAIL firmware error=%h",dut.debug_regs[1]);
      if (event_code!=32'h100 && event_code!=32'h200 && event_code!=32'h1ff) begin
        if (dut.debug_regs[2]!==current_case ||
            dut.debug_regs[4]!==input_fixture[current_input_offset+5] ||
            dut.debug_regs[5]!==input_fixture[current_input_offset+1] ||
            dut.debug_regs[6]!==input_fixture[current_input_offset+4] ||
            dut.debug_regs[7]!==input_sizes[current_case])
          $fatal(1,"MLKEM512_FAIL metadata changed during case=%0d",current_case);
      end
    end
  endtask

  task automatic check_stream(input integer is_output);
    reg [31:0] payload, wanted;
    integer byte_count, fixture_offset, b;
    begin
      byte_count=is_output ? output_sizes[current_case] : input_sizes[current_case];
      fixture_offset=is_output ? current_expected_offset+12 : current_input_offset+12;
      if (stream_words>=byte_count/4 || dut.debug_regs[12]!==stream_words || dut.debug_regs[14]!==4)
        $fatal(1,"MLKEM512_FAIL stream shape case=%0d output=%0d word=%0d index=%h valid=%h",current_case,is_output,stream_words,dut.debug_regs[12],dut.debug_regs[14]);
      payload=dut.debug_regs[13];
      wanted=is_output ? expected_fixture[fixture_offset+stream_words] : input_fixture[fixture_offset+stream_words];
      for (b=0;b<4;b=b+1) begin
        if (payload[8*b+:8]!==wanted[8*b+:8])
          $fatal(1,"MLKEM512_FAIL byte mismatch case=%0d output=%0d byte=%0d got=%h expected=%h",current_case,is_output,4*stream_words+b,payload[8*b+:8],wanted[8*b+:8]);
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
        $fatal(1,"MLKEM512_FAIL cycle boundary case=%0d samples=%0d firmware=%h observed=%0d empty=%0d",current_case,rdcycle_samples,dut.debug_regs[3],algorithm_cycles,empty_cycles);
      if (dut.debug_regs[9]!==expected_fixture[current_expected_offset+11])
        $fatal(1,"MLKEM512_FAIL API return case=%0d got=%h expected=%h",current_case,dut.debug_regs[9],expected_fixture[current_expected_offset+11]);
      // Validation-only cases legitimately execute no multiply instruction.
      if ((EXPECT_M==0 && m_total!=0) ||
          (EXPECT_M==1 && input_fixture[current_input_offset+5]<=4 && m_count[0]==0))
        $fatal(1,"MLKEM512_FAIL unexpected M execution case=%0d expected=%0d total=%0d",current_case,EXPECT_M,m_total);
    end
  endtask

  task automatic reset_profile;
    integer phase;
    begin
      profile_depth=0; profile_max_depth=0;
      profile_enters=0; profile_exits=0;
      for (phase=0;phase<PROFILE_PHASES;phase=phase+1) begin
        profile_exclusive[phase]=0; profile_inclusive[phase]=0;
        profile_calls[phase]=0; profile_completed[phase]=0;
      end
    end
  endtask

  task automatic profile_marker(input [31:0] marker);
    integer phase;
    reg [31:0] kind;
    begin
      if (state!=MEASURE || !algorithm_active || rdcycle_samples!=1)
        $fatal(1,"PROFILE_FAIL marker outside measured algorithm case=%0d marker=%h",current_case,marker);
      if ((^marker)===1'bx)
        $fatal(1,"PROFILE_FAIL unknown marker bits case=%0d marker=%h",current_case,marker);
      phase=marker[5:0]; kind=marker & 32'hffffffc0;
      if (phase==0 || phase>=PROFILE_PHASES ||
          (kind!=32'h30000000 && kind!=32'h40000000))
        $fatal(1,"PROFILE_FAIL malformed marker case=%0d marker=%h",current_case,marker);
      if (kind==32'h30000000) begin
        if (profile_depth>=PROFILE_STACK_LIMIT)
          $fatal(1,"PROFILE_FAIL scope stack overflow case=%0d phase=%0d",current_case,phase);
        profile_stack[profile_depth]=phase;
        profile_start[profile_depth]=cycle_count;
        profile_depth=profile_depth+1;
        if (profile_depth>profile_max_depth) profile_max_depth=profile_depth;
        profile_calls[phase]=profile_calls[phase]+1;
        profile_enters=profile_enters+1;
      end else begin
        if (profile_depth==0)
          $fatal(1,"PROFILE_FAIL scope stack underflow case=%0d phase=%0d",current_case,phase);
        if (profile_stack[profile_depth-1]!=phase)
          $fatal(1,"PROFILE_FAIL nonnested exit case=%0d phase=%0d expected=%0d",current_case,phase,profile_stack[profile_depth-1]);
        profile_depth=profile_depth-1;
        profile_inclusive[phase]=profile_inclusive[phase]+cycle_count-profile_start[profile_depth];
        profile_completed[phase]=profile_completed[phase]+1;
        profile_exits=profile_exits+1;
      end
    end
  endtask

  task automatic report_profile;
    integer phase;
    longint unsigned accounted, calls, completed;
    begin
      accounted=0; calls=0; completed=0;
      if (profile_depth!=0 || profile_enters!=profile_exits)
        $fatal(1,"PROFILE_FAIL unbalanced scopes case=%0d depth=%0d enters=%0d exits=%0d",current_case,profile_depth,profile_enters,profile_exits);
      profile_inclusive[0]=profile_exclusive[0];
      for (phase=0;phase<PROFILE_PHASES;phase=phase+1) begin
        accounted=accounted+profile_exclusive[phase];
        calls=calls+profile_calls[phase]; completed=completed+profile_completed[phase];
        if (profile_calls[phase]!=profile_completed[phase] ||
            profile_exclusive[phase]>profile_inclusive[phase] ||
            (phase==0 && profile_calls[phase]!=0) ||
            (phase!=0 && profile_calls[phase]==0 &&
             (profile_exclusive[phase]!=0 || profile_inclusive[phase]!=0)))
          $fatal(1,"PROFILE_FAIL inconsistent phase totals case=%0d phase=%0d",current_case,phase);
      end
      if (accounted!=algorithm_cycles || calls!=profile_enters || completed!=profile_exits)
        $fatal(1,"PROFILE_FAIL accounting case=%0d cycles=%0d accounted=%0d calls=%0d completed=%0d",current_case,algorithm_cycles,accounted,calls,completed);
      for (phase=0;phase<PROFILE_PHASES;phase=phase+1)
        $display("PROFILE_ROW,%0d,%0d,%0d,%0d,%0d",current_case,phase,profile_exclusive[phase],profile_inclusive[phase],profile_calls[phase]);
      $display("PROFILE_CASE,%0d,%0d,%0d,%0d,%0d,%0d",current_case,algorithm_cycles,accounted,profile_enters,profile_exits,profile_max_depth);
    end
  endtask

  initial begin
    if (PROFILE_PHASES<2 || PROFILE_PHASES>64)
      $fatal(1,"PROFILE_FAIL PROFILE_PHASES must be in 2..64");
    if ((EXPECT_M!=0 && EXPECT_M!=1) ||
        (EXPECT_M==1 && (!(CPU_ENABLE_MUL || CPU_ENABLE_FAST_MUL) || !CPU_ENABLE_DIV)))
      $fatal(1,"MLKEM512_FAIL invalid CPU/firmware configuration");
    for (j=0;j<8;j=j+1) m_count[j]=0;
    vector_file=$fopen("mlkem512_input.mem","r");
    if (!vector_file) $fatal(1,"MLKEM512_FAIL missing input fixture");
    while (!$feof(vector_file)) begin
      scan_result=$fscanf(vector_file,"%h",file_word);
      if (scan_result==1) begin
        if (input_words_read>=MAX_WORDS || (^file_word)===1'bx)
          $fatal(1,"MLKEM512_FAIL oversized/unknown input fixture");
        input_fixture[input_words_read]=file_word; input_words_read=input_words_read+1;
      end else if (!$feof(vector_file)) $fatal(1,"MLKEM512_FAIL malformed input fixture");
    end
    $fclose(vector_file);
    vector_file=$fopen("mlkem512_expected.mem","r");
    if (!vector_file) $fatal(1,"MLKEM512_FAIL missing expected fixture");
    while (!$feof(vector_file)) begin
      scan_result=$fscanf(vector_file,"%h",file_word);
      if (scan_result==1) begin
        if (expected_words_read>=MAX_WORDS || (^file_word)===1'bx)
          $fatal(1,"MLKEM512_FAIL oversized/unknown expected fixture");
        expected_fixture[expected_words_read]=file_word; expected_words_read=expected_words_read+1;
      end else if (!$feof(vector_file)) $fatal(1,"MLKEM512_FAIL malformed expected fixture");
    end
    $fclose(vector_file);
    if (input_words_read<8 || expected_words_read<8) $fatal(1,"MLKEM512_FAIL truncated header");
    fixture_cases=input_fixture[3];
    if (EXPECTED_CASES<1 || EXPECTED_CASES>MAX_CASES || fixture_cases!=EXPECTED_CASES || input_fixture[4]!==input_words_read || expected_fixture[4]!==expected_words_read)
      $fatal(1,"MLKEM512_FAIL fixture size/case count mismatch");
    for (j=0;j<8;j=j+1)
      if (j!=4 && input_fixture[j]!==expected_fixture[j]) $fatal(1,"MLKEM512_FAIL header mismatch word=%0d",j);
    if (input_fixture[0]!==32'h3254414b || input_fixture[1]!==1 || input_fixture[2]!==512 ||
        input_fixture[5]!==0 || input_fixture[6]!==0 || input_fixture[7]!==0)
      $fatal(1,"MLKEM512_FAIL invalid header");
    pos_in=8; pos_out=8;
    for (j=0;j<fixture_cases;j=j+1) begin
      if (pos_in+12>input_words_read || pos_out+12>expected_words_read)
        $fatal(1,"MLKEM512_FAIL truncated metadata case=%0d",j);
      input_offsets[j]=pos_in; expected_offsets[j]=pos_out;
      for (k=0;k<11;k=k+1)
        if (input_fixture[pos_in+k]!==expected_fixture[pos_out+k])
          $fatal(1,"MLKEM512_FAIL metadata mismatch case=%0d word=%0d",j,k);
      if (input_fixture[pos_in]!==j || input_fixture[pos_in+11]!==0 ||
          input_fixture[pos_in+5]<1 || input_fixture[pos_in+5]>6)
        $fatal(1,"MLKEM512_FAIL invalid case identity/operation case=%0d",j);
      for (k=6;k<11;k=k+1)
        if (input_fixture[pos_in+k]>4096 || input_fixture[pos_in+k]%4!=0)
          $fatal(1,"MLKEM512_FAIL invalid payload size case=%0d word=%0d",j,k);
      case (input_fixture[pos_in+5])
        1: if (input_fixture[pos_in+6]!==32 || input_fixture[pos_in+7]!==32 || input_fixture[pos_in+8]!==0 || input_fixture[pos_in+9]!==800 || input_fixture[pos_in+10]!==1632) $fatal(1,"MLKEM512_FAIL KeyGen shape");
        2: if (input_fixture[pos_in+6]!==800 || input_fixture[pos_in+7]!==32 || input_fixture[pos_in+8]!==0 || input_fixture[pos_in+9]!==768 || input_fixture[pos_in+10]!==32) $fatal(1,"MLKEM512_FAIL Encaps shape");
        3: if (input_fixture[pos_in+6]!==1632 || input_fixture[pos_in+7]!==768 || input_fixture[pos_in+8]!==0 || input_fixture[pos_in+9]!==32 || input_fixture[pos_in+10]!==0) $fatal(1,"MLKEM512_FAIL Decaps shape");
        4: if (input_fixture[pos_in+6]!==32 || input_fixture[pos_in+7]!==32 || input_fixture[pos_in+8]!==768 || input_fixture[pos_in+9]!==32 || input_fixture[pos_in+10]!==0) $fatal(1,"MLKEM512_FAIL seeded Decaps shape");
        5: if (input_fixture[pos_in+6]!==800 || input_fixture[pos_in+7]!==0 || input_fixture[pos_in+8]!==0 || input_fixture[pos_in+9]!==0 || input_fixture[pos_in+10]!==0) $fatal(1,"MLKEM512_FAIL public-key check shape");
        6: if (input_fixture[pos_in+6]!==1632 || input_fixture[pos_in+7]!==0 || input_fixture[pos_in+8]!==0 || input_fixture[pos_in+9]!==0 || input_fixture[pos_in+10]!==0) $fatal(1,"MLKEM512_FAIL secret-key check shape");
      endcase
      if (expected_fixture[pos_out+11]!==0 && expected_fixture[pos_out+11]!==32'hfffffffc && expected_fixture[pos_out+11]!==32'hfffffffb)
        $fatal(1,"MLKEM512_FAIL unsupported expected API return case=%0d",j);
      input_sizes[j]=input_fixture[pos_in+6]+input_fixture[pos_in+7]+input_fixture[pos_in+8];
      output_sizes[j]=input_fixture[pos_in+9]+input_fixture[pos_in+10];
      expected_input_bytes=expected_input_bytes+input_sizes[j];
      expected_output_bytes=expected_output_bytes+output_sizes[j];
      pos_in=pos_in+12+input_sizes[j]/4; pos_out=pos_out+12+output_sizes[j]/4;
      if (pos_in>input_words_read || pos_out>expected_words_read) $fatal(1,"MLKEM512_FAIL truncated payload case=%0d",j);
    end
    if (pos_in!=input_words_read || pos_out!=expected_words_read) $fatal(1,"MLKEM512_FAIL trailing fixture data");
    $display("MLKEM512_HEADER,index,dataset,vsId,tgId,tcId,op,return_code,raw_cycles,empty_cycles,input_bytes,output_bytes,m_total,mul,mulh,mulhsu,mulhu,div,divu,rem,remu,min_sp");
    $display("PROFILE_HEADER,index,phase,exclusive_cycles,inclusive_cycles,calls");
    $display("PROFILE_CASE_HEADER,index,cycles,accounted,enters,exits,max_depth");
    $display("MLKEM512_START cases=%0d ram_bytes=65536 stack_bytes=16384 clock_mhz=100 mul=%0d fast_mul=%0d div=%0d expect_m=%0d",fixture_cases,CPU_ENABLE_MUL,CPU_ENABLE_FAST_MUL,CPU_ENABLE_DIV,EXPECT_M);
    repeat (32) @(negedge clk);
    resetn=1;
  end

  // A host response at the opposite clock edge cannot race CPU/MMIO writes.
  // Only the two dedicated mailbox registers are driven by the testbench.
  always @(negedge clk) begin
    if (resetn && pending_request>=0) begin
      dut.debug_regs[10]=input_fixture[pending_request];
      dut.debug_regs[11]=pending_request+1;
      pending_request=-1;
    end
  end

  always @(posedge clk) begin
    if (resetn) begin
      cycle_count=cycle_count+1;
      if (cycle_count-case_start_cycle>=TIMEOUT_CYCLES)
        $fatal(1,"MLKEM512_FAIL timeout cycle=%0d case=%0d state=%0d pc=%h sp=%h",cycle_count,current_case,state,dut.cpu.picorv32_core.reg_pc,observed_sp);
      if (trap!==1'b0) $fatal(1,"MLKEM512_FAIL CPU trap=%b pc=%h",trap,dut.cpu.picorv32_core.reg_pc);
      if (status===STATUS_FAIL) $fatal(1,"MLKEM512_FAIL firmware error=%h",dut.debug_regs[1]);
      if (dut.c_arvalid===1'b1 && valid_address(dut.c_araddr)!==1'b1) $fatal(1,"MLKEM512_FAIL out-of-map read %h",dut.c_araddr);
      if (dut.c_awvalid===1'b1 && valid_address(dut.c_awaddr)!==1'b1) $fatal(1,"MLKEM512_FAIL out-of-map write %h",dut.c_awaddr);
      if (status===STATUS_RUN) stack_monitor_active=1;
      if (stack_monitor_active) begin
        if ((^observed_sp)===1'bx || observed_sp<STACK_BOTTOM || observed_sp>STACK_TOP || observed_sp[3:0]!=0)
          $fatal(1,"MLKEM512_FAIL invalid stack pointer %h case=%0d",observed_sp,current_case);
        if (observed_sp<minimum_sp) minimum_sp=observed_sp;
        if (algorithm_active && observed_sp<algorithm_minimum_sp) algorithm_minimum_sp=observed_sp;
      end
      if (rdcycle_executing) begin
        if (state==MEASURE) begin
          if (rdcycle_samples==0) begin
            algorithm_start=dut.cpu.picorv32_core.count_cycle[31:0];
            algorithm_active=1; algorithm_minimum_sp=observed_sp;
          end else if (rdcycle_samples==1) begin
            if (profile_depth!=0)
              $fatal(1,"PROFILE_FAIL active scope at algorithm end case=%0d depth=%0d",current_case,profile_depth);
            algorithm_cycles=dut.cpu.picorv32_core.count_cycle[31:0]-algorithm_start;
            algorithm_active=0;
          end else $fatal(1,"MLKEM512_FAIL extra rdcycle in algorithm");
          rdcycle_samples=rdcycle_samples+1;
        end else if (state==WAIT_CASE && completed_cases==0 && calibration_samples<2) begin
          if (calibration_samples==0) calibration_start=dut.cpu.picorv32_core.count_cycle[31:0];
          else observed_empty=dut.cpu.picorv32_core.count_cycle[31:0]-calibration_start;
          calibration_samples=calibration_samples+1;
        end else $fatal(1,"MLKEM512_FAIL rdcycle outside measurement window");
      end
      if (dut.cpu.picorv32_core.pcpi_valid && dut.cpu.picorv32_core.pcpi_int_ready) begin
        if (observed_insn[31:25]!==7'b0000001 || observed_insn[6:0]!==7'b0110011 || (^observed_insn[14:12])===1'bx)
          $fatal(1,"MLKEM512_FAIL unexpected PCPI instruction %h",observed_insn);
        operation=observed_insn[14:12]; all_m_total=all_m_total+1;
        if (EXPECT_M==0) $fatal(1,"MLKEM512_FAIL RV32I executed M instruction");
        if (algorithm_active) begin m_count[operation]=m_count[operation]+1; m_total=m_total+1; end
      end
      if (dut.local_write_commit && dut.commit_addr[31:6]==DEBUG_BASE[31:6]) begin
        if (dut.commit_strb!==4'b1111 || dut.commit_addr[1:0]!==0) $fatal(1,"MLKEM512_FAIL partial/unaligned debug write");
        if (dut.commit_addr==DEBUG_BASE+40 || dut.commit_addr==DEBUG_BASE+44) $fatal(1,"MLKEM512_FAIL CPU wrote host mailbox");
        if (algorithm_active && dut.commit_addr!=DEBUG_BASE+56)
          $fatal(1,"MLKEM512_FAIL debug write inside timed algorithm");
        // debug_regs[14] carries zero valid bytes for case boundary records,
        // or four for data streams. Other values must be valid timed markers.
        if (dut.commit_addr==DEBUG_BASE+56 &&
            (algorithm_active || state==MEASURE ||
             (dut.commit_data!==32'd0 && dut.commit_data!==32'd4)))
          profile_marker(dut.commit_data);
        if (dut.commit_addr==DEBUG_BASE+60) begin
          case (dut.commit_data)
            32'h200: begin
              require_state(WAIT_CASE,32'h200);
              if (pending_request!=-1 || requested_words>=input_words_read || completed_cases>=fixture_cases ||
                  dut.debug_regs[12]!==requested_words ||
                  requested_words>=input_offsets[completed_cases]+12+input_sizes[completed_cases]/4)
                $fatal(1,"MLKEM512_FAIL invalid mailbox request requested=%0d index=%h case=%0d",requested_words,dut.debug_regs[12],completed_cases);
              pending_request=requested_words; requested_words=requested_words+1;
            end
            32'h100: begin
              require_state(WAIT_CASE,32'h100);
              if (completed_cases>=fixture_cases || pending_request!=-1 || !stack_monitor_active || calibration_samples!=2)
                $fatal(1,"MLKEM512_FAIL premature case begin");
              current_case=completed_cases; current_input_offset=input_offsets[current_case]; current_expected_offset=expected_offsets[current_case];
              if (requested_words!=current_input_offset+12+input_sizes[current_case]/4 ||
                  dut.debug_regs[2]!==current_case || dut.debug_regs[4]!==input_fixture[current_input_offset+5] ||
                  dut.debug_regs[5]!==input_fixture[current_input_offset+1] || dut.debug_regs[6]!==input_fixture[current_input_offset+4] ||
                  dut.debug_regs[7]!==input_sizes[current_case] || dut.debug_regs[8]!==observed_empty || observed_empty==0 ||
                  dut.debug_regs[3]!==0 || dut.debug_regs[9]!==0)
                $fatal(1,"MLKEM512_FAIL invalid case metadata/calibration case=%0d",current_case);
              empty_cycles=dut.debug_regs[8]; case_input_checks=0; case_output_checks=0;
              stream_words=0; rdcycle_samples=0; m_total=0;
              for (j=0;j<8;j=j+1) m_count[j]=0;
              reset_profile();
              state=ECHO_INPUT;
            end
            32'h201: begin
              require_state(ECHO_INPUT,32'h201); check_stream(0);
              if (stream_words==input_sizes[current_case]/4) begin stream_words=0; state=WAIT_MEASURE; end
            end
            32'h108: begin
              require_state(WAIT_MEASURE,32'h108);
              if (case_input_checks!=input_sizes[current_case] || rdcycle_samples!=0 || algorithm_active)
                $fatal(1,"MLKEM512_FAIL premature/nested measurement case=%0d",current_case);
              state=MEASURE;
            end
            32'h109: begin
              require_state(MEASURE,32'h109);
              if (rdcycle_samples!=2 || algorithm_active || algorithm_cycles<=empty_cycles)
                $fatal(1,"MLKEM512_FAIL missing/invalid rdcycle pair case=%0d",current_case);
              state=output_sizes[current_case]==0 ? WAIT_END : OUTPUT_DATA;
            end
            32'h202: begin
              require_state(OUTPUT_DATA,32'h202); check_metrics(); check_stream(1);
              if (stream_words==output_sizes[current_case]/4) begin stream_words=0; state=WAIT_END; end
            end
            32'h105: begin
              require_state(WAIT_END,32'h105); check_metrics();
              if (case_input_checks!=input_sizes[current_case] || case_output_checks!=output_sizes[current_case])
                $fatal(1,"MLKEM512_FAIL incomplete case bytes case=%0d",current_case);
              report_profile();
              $display("MLKEM512_ROW,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0x%08h",
                current_case,input_fixture[current_input_offset+1],input_fixture[current_input_offset+2],input_fixture[current_input_offset+3],input_fixture[current_input_offset+4],input_fixture[current_input_offset+5],$signed(dut.debug_regs[9]),
                algorithm_cycles,empty_cycles,case_input_checks,case_output_checks,m_total,m_count[0],m_count[1],m_count[2],m_count[3],m_count[4],m_count[5],m_count[6],m_count[7],algorithm_minimum_sp);
              completed_cases=completed_cases+1; state=WAIT_CASE; case_start_cycle=cycle_count;
            end
            32'h1ff: begin
              require_state(WAIT_CASE,32'h1ff);
              if (completed_cases!=fixture_cases || input_checks!=expected_input_bytes || output_checks!=expected_output_bytes ||
                  requested_words!=input_words_read || pending_request!=-1 || status!==STATUS_PASS || algorithm_active)
                $fatal(1,"MLKEM512_FAIL premature completion cases=%0d inputs=%0d outputs=%0d requests=%0d status=%h",completed_cases,input_checks,output_checks,requested_words,status);
              $display("MLKEM512_PASS cases=%0d input_bytes=%0d output_bytes=%0d cpu_mul=%0d cpu_fast_mul=%0d cpu_div=%0d expect_m=%0d cycles=%0d all_m=%0d min_sp=0x%08h stack_used=%0d",
                completed_cases,input_checks,output_checks,CPU_ENABLE_MUL,CPU_ENABLE_FAST_MUL,CPU_ENABLE_DIV,EXPECT_M,cycle_count,all_m_total,minimum_sp,STACK_TOP-minimum_sp);
              $finish;
            end
            default: $fatal(1,"MLKEM512_FAIL unknown event=%h",dut.commit_data);
          endcase
        end
      end
      // Start rdcycle activates charging on its own edge; stop rdcycle clears
      // it before charging, exactly matching the original raw cycle delta.
      if (algorithm_active) begin
        profile_owner=profile_depth==0 ? 0 : profile_stack[profile_depth-1];
        profile_exclusive[profile_owner]=profile_exclusive[profile_owner]+1;
      end
    end
  end
endmodule
