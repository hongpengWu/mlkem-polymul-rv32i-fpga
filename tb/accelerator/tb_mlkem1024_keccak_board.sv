`timescale 1ns/1ps

// Only board pins are driven. The real MMCM, reset synchronizer, CPU firmware,
// BRAM and HLS accelerator execute; no simulator mailbox or internal force.
module tb_mlkem1024_keccak_board;
    localparam integer MAX_WORDS=16384;
    localparam [31:0] DEBUG_BASE=32'h50000000;
    localparam [31:0] STATUS_RUN=32'h4b415452, STATUS_PASS=32'h4b415450;
    localparam [31:0] STATUS_FAIL=32'h4b415446;
    localparam integer WAIT_CASE=0, INPUT_DATA=1, WAIT_MEASURE=2;
    localparam integer MEASURE=3, OUTPUT_DATA=4, WAIT_END=5;
    reg sys_clk=0, btn0=1;
    wire [3:0] led;
    always #4 sys_clk=~sys_clk;
    mlkem1024_keccak_pynqz2_top dut(.sys_clk(sys_clk),.btn0(btn0),.led(led));

    reg [31:0] input_fixture[0:MAX_WORDS-1], expected_fixture[0:MAX_WORDS-1];
    integer input_offset[0:2], expected_offset[0:2];
    integer input_size[0:2], output_size[0:2];
    integer input_words=0, expected_words=0, expected_input_bytes=0, expected_output_bytes=0;
    integer f, scan, i, j, pin, pout;
    reg [31:0] word_value;
    integer state=WAIT_CASE, completed=0, stream_words=0;
    integer input_checks=0, output_checks=0, hls_starts=0, hls_dones=0;
    integer hash_calls=0, squeeze_calls=0, resets=0, releases=0;
    integer stable_release_edges=0, measured_samples=0;
    integer case_first_starts=0, case_first_dones=0;
    reg previous_start=0, previous_done=0;
    reg [31:0] measure_begin=0, measured_cycles=0;
    longint unsigned cycles=0;
    realtime last_clk_edge=0, prior_locked_edge=0;

    initial begin
        f=$fopen("board_input.mem","r");
        if (!f) $fatal(1,"BOARD_KAT_FAIL missing input fixture");
        while (!$feof(f)) begin
            scan=$fscanf(f,"%h",word_value);
            if (scan==1) begin
                if (input_words>=MAX_WORDS || (^word_value)===1'bx)
                    $fatal(1,"BOARD_KAT_FAIL invalid input fixture");
                input_fixture[input_words]=word_value; input_words=input_words+1;
            end else if (!$feof(f)) $fatal(1,"BOARD_KAT_FAIL malformed input fixture");
        end
        $fclose(f);
        f=$fopen("board_expected.mem","r");
        if (!f) $fatal(1,"BOARD_KAT_FAIL missing expected fixture");
        while (!$feof(f)) begin
            scan=$fscanf(f,"%h",word_value);
            if (scan==1) begin
                if (expected_words>=MAX_WORDS || (^word_value)===1'bx)
                    $fatal(1,"BOARD_KAT_FAIL invalid expected fixture");
                expected_fixture[expected_words]=word_value; expected_words=expected_words+1;
            end else if (!$feof(f)) $fatal(1,"BOARD_KAT_FAIL malformed expected fixture");
        end
        $fclose(f);
        if (input_words<8 || expected_words<8 || input_fixture[0]!==32'h3254414b ||
            input_fixture[1]!==1 || input_fixture[2]!==1024 || input_fixture[3]!==3 ||
            input_fixture[4]!==input_words || expected_fixture[4]!==expected_words)
            $fatal(1,"BOARD_KAT_FAIL fixture header");
        for (i=0;i<8;i=i+1)
            if (i!=4 && input_fixture[i]!==expected_fixture[i])
                $fatal(1,"BOARD_KAT_FAIL mismatched fixture header");
        pin=8; pout=8;
        for (i=0;i<3;i=i+1) begin
            if (pin+12>input_words || pout+12>expected_words)
                $fatal(1,"BOARD_KAT_FAIL truncated metadata");
            input_offset[i]=pin; expected_offset[i]=pout;
            for (j=0;j<11;j=j+1)
                if (input_fixture[pin+j]!==expected_fixture[pout+j])
                    $fatal(1,"BOARD_KAT_FAIL mismatched case metadata");
            if (input_fixture[pin]!==i || input_fixture[pin+11]!==0 ||
                input_fixture[pin+5]!==((i==0)?1:((i==1)?2:3)) ||
                expected_fixture[pout+11]!==0)
                $fatal(1,"BOARD_KAT_FAIL subset identity/operation/return");
            for (j=6;j<11;j=j+1)
                if (input_fixture[pin+j]>4096 || input_fixture[pin+j]%4!=0)
                    $fatal(1,"BOARD_KAT_FAIL payload shape");
            input_size[i]=input_fixture[pin+6]+input_fixture[pin+7]+input_fixture[pin+8];
            output_size[i]=input_fixture[pin+9]+input_fixture[pin+10];
            expected_input_bytes=expected_input_bytes+input_size[i];
            expected_output_bytes=expected_output_bytes+output_size[i];
            pin=pin+12+input_size[i]/4; pout=pout+12+output_size[i]/4;
            if (pin>input_words || pout>expected_words)
                $fatal(1,"BOARD_KAT_FAIL truncated payload");
        end
        if (pin!=input_words || pout!=expected_words)
            $fatal(1,"BOARD_KAT_FAIL trailing fixture data");
        repeat(40) @(negedge sys_clk);
        #1 btn0=0;
        wait(dut.resetn===1'b1);
        wait(dut.system_i.adapter_i.busy && dut.system_i.adapter_i.hls_i.ap_start);
        repeat(4) @(posedge dut.clk100);
        @(negedge dut.clk100);
        #1;
        if (!dut.system_i.adapter_i.busy)
            $fatal(1,"BOARD_KAT_FAIL reset injection missed active accelerator");
        resets=resets+1;
        btn0=1;
        #0.001;
        if (dut.reset_sync!==4'b0000 || dut.resetn!==1'b1)
            $fatal(1,"BOARD_KAT_FAIL async request bypassed synchronous system reset");
        @(posedge dut.clk100);
        #0.001;
        if (dut.resetn!==1'b0) $fatal(1,"BOARD_KAT_FAIL system reset missed next clock edge");
        repeat(16) @(negedge dut.clk100);
        if (dut.system_i.adapter_i.starts_reg!==0 || dut.system_i.adapter_i.busy!==0 ||
            dut.system_i.status_out!==0 || led[2:0]!==0)
            $fatal(1,"BOARD_KAT_FAIL active reset did not clear controls");
        #1 btn0=0;
        wait(dut.resetn===1'b1);
        $display("BOARD_RESET_PASS busy_abort=1 releases=%0d real_mmcm=1",releases);
    end

    // Wall-clock simulation guard also catches a non-locking/absent MMCM clock.
    initial begin #400000000; $fatal(1,"BOARD_KAT_FAIL global timeout"); end
    always @(posedge dut.clk100) begin
        last_clk_edge=$realtime;
        if (dut.locked) begin
            if (prior_locked_edge!=0 &&
                (($realtime-prior_locked_edge)<9.998 || ($realtime-prior_locked_edge)>10.002))
                $fatal(1,"BOARD_KAT_FAIL generated clock period=%0.3f",$realtime-prior_locked_edge);
            prior_locked_edge=$realtime;
        end else prior_locked_edge=0;
        if (dut.reset_request) stable_release_edges=0;
        else stable_release_edges=stable_release_edges+1;
    end
    always @(posedge dut.resetn) begin
        if ($realtime!=last_clk_edge || stable_release_edges<5 || btn0 || !dut.locked)
            $fatal(1,"BOARD_KAT_FAIL asynchronous/early reset release");
        releases=releases+1;
    end
    always @(negedge dut.resetn) begin
        if ($realtime!=last_clk_edge)
            $fatal(1,"BOARD_KAT_FAIL asynchronous system reset assertion");
    end

    task automatic require_state(input integer required);
        begin
            if (state!=required || completed>=3 || dut.status!==STATUS_RUN ||
                dut.system_i.debug_regs[1]!==0 || dut.system_i.debug_regs[2]!==completed ||
                dut.system_i.debug_regs[4]!==input_fixture[input_offset[completed]+5] ||
                dut.system_i.debug_regs[5]!==input_fixture[input_offset[completed]+1] ||
                dut.system_i.debug_regs[6]!==input_fixture[input_offset[completed]+4] ||
                dut.system_i.debug_regs[7]!==input_size[completed])
                $fatal(1,"BOARD_KAT_FAIL state/metadata case=%0d state=%0d",completed,state);
        end
    endtask
    task automatic check_stream(input integer is_output);
        integer count_bytes, base, b;
        reg [31:0] expected_word, actual_word;
        begin
            count_bytes=is_output?output_size[completed]:input_size[completed];
            base=is_output?expected_offset[completed]+12:input_offset[completed]+12;
            if (stream_words>=count_bytes/4 || dut.system_i.debug_regs[12]!==stream_words ||
                dut.system_i.debug_regs[14]!==4)
                $fatal(1,"BOARD_KAT_FAIL stream shape case=%0d",completed);
            expected_word=is_output?expected_fixture[base+stream_words]:input_fixture[base+stream_words];
            actual_word=dut.system_i.debug_regs[13];
            for (b=0;b<4;b=b+1)
                if (actual_word[8*b+:8]!==expected_word[8*b+:8])
                    $fatal(1,"BOARD_KAT_FAIL byte case=%0d output=%0d byte=%0d got=%h expected=%h",
                        completed,is_output,stream_words*4+b,actual_word[8*b+:8],expected_word[8*b+:8]);
            if (is_output) output_checks=output_checks+4;
            else input_checks=input_checks+4;
            stream_words=stream_words+1;
        end
    endtask

    always @(posedge dut.clk100) begin
        if (!dut.resetn) begin
            state=WAIT_CASE; completed=0; stream_words=0; cycles=0;
            input_checks=0; output_checks=0; hls_starts=0; hls_dones=0;
            hash_calls=0; squeeze_calls=0; previous_start=0; previous_done=0;
            measured_samples=0; measured_cycles=0; measure_begin=0;
            case_first_starts=0; case_first_dones=0;
        end else begin
            cycles=cycles+1;
            if (cycles>30000000) $fatal(1,"BOARD_KAT_FAIL execution timeout");
            if (dut.trap!==0 || dut.status===STATUS_FAIL || dut.system_i.adapter_i.error)
                $fatal(1,"BOARD_KAT_FAIL trap/status/adapter error status=%h error=%h",dut.status,dut.system_i.debug_regs[1]);
            if (dut.system_i.adapter_i.hls_i.ap_start && !previous_start) begin
                if (state!=MEASURE) $fatal(1,"BOARD_KAT_FAIL HLS start outside API");
                hls_starts=hls_starts+1;
                case (dut.system_i.adapter_i.command_shadow)
                    0: hash_calls=hash_calls+1;
                    1: squeeze_calls=squeeze_calls+1;
                    default: $fatal(1,"BOARD_KAT_FAIL invalid HLS command");
                endcase
            end
            if (dut.system_i.adapter_i.hls_i.ap_done && !previous_done) hls_dones=hls_dones+1;
            previous_start=dut.system_i.adapter_i.hls_i.ap_start;
            previous_done=dut.system_i.adapter_i.hls_i.ap_done;
            if (state==MEASURE && dut.system_i.cpu.picorv32_core.cpu_state==8'b00100000 &&
                dut.system_i.cpu.picorv32_core.instr_rdcycle) begin
                if (measured_samples==0) measure_begin=dut.system_i.cpu.picorv32_core.count_cycle[31:0];
                else if (measured_samples==1)
                    measured_cycles=dut.system_i.cpu.picorv32_core.count_cycle[31:0]-measure_begin;
                else $fatal(1,"BOARD_KAT_FAIL extra API rdcycle");
                measured_samples=measured_samples+1;
            end
            if (dut.system_i.local_write_commit && dut.system_i.commit_addr[31:6]==DEBUG_BASE[31:6]) begin
                if (dut.system_i.commit_strb!==4'hf || dut.system_i.commit_addr[1:0]!==0)
                    $fatal(1,"BOARD_KAT_FAIL partial/unaligned debug write");
                if (dut.system_i.commit_addr==DEBUG_BASE+60) begin
                    case (dut.system_i.commit_data)
                        32'h100: begin
                            require_state(WAIT_CASE); state=INPUT_DATA; stream_words=0;
                            measured_samples=0; measured_cycles=0;
                            case_first_starts=hls_starts; case_first_dones=hls_dones;
                        end
                        32'h201: begin
                            require_state(INPUT_DATA); check_stream(0);
                            if (stream_words==input_size[completed]/4) begin stream_words=0; state=WAIT_MEASURE; end
                        end
                        32'h108: begin require_state(WAIT_MEASURE); state=MEASURE; end
                        32'h109: begin
                            require_state(MEASURE);
                            if (measured_samples!=2 || measured_cycles<=dut.system_i.debug_regs[8])
                                $fatal(1,"BOARD_KAT_FAIL missing API cycle measurement");
                            state=OUTPUT_DATA;
                        end
                        32'h202: begin
                            require_state(OUTPUT_DATA); check_stream(1);
                            if (stream_words==output_size[completed]/4) begin stream_words=0; state=WAIT_END; end
                        end
                        32'h105: begin
                            require_state(WAIT_END);
                            if (dut.system_i.debug_regs[3]!==measured_cycles ||
                                dut.system_i.debug_regs[9]!==expected_fixture[expected_offset[completed]+11] ||
                                hls_starts!=hls_dones || hls_starts==case_first_starts ||
                                hls_starts-case_first_starts!=hls_dones-case_first_dones ||
                                dut.system_i.adapter_i.starts_reg!==hls_starts || dut.system_i.adapter_i.busy)
                                $fatal(1,"BOARD_KAT_FAIL API return/cycles/HLS metrics");
                            $display("BOARD_KAT_ROW case=%0d op=%0d cycles=%0d starts=%0d input_bytes=%0d output_bytes=%0d",
                                completed,dut.system_i.debug_regs[4],measured_cycles,hls_starts-case_first_starts,input_size[completed],output_size[completed]);
                            completed=completed+1; state=WAIT_CASE;
                        end
                        32'h1ff: begin
                            if (state!=WAIT_CASE || completed!=3 || resets!=1 || releases!=2 ||
                                input_checks!=expected_input_bytes || output_checks!=expected_output_bytes ||
                                dut.status!==STATUS_PASS || led!==4'b0001 ||
                                hls_starts!=85 || hls_dones!=85 || hash_calls!=81 || squeeze_calls!=4 ||
                                dut.system_i.adapter_i.starts_reg!==85 || dut.system_i.adapter_i.busy)
                                $fatal(1,"BOARD_KAT_FAIL incomplete final evidence");
                            $display("BOARD_KAT_PASS cases=3 starts=85 resets=1 input_bytes=%0d output_bytes=%0d hash=%0d squeeze=%0d cycles=%0d",
                                input_checks,output_checks,hash_calls,squeeze_calls,cycles);
                            $finish;
                        end
                        default: $fatal(1,"BOARD_KAT_FAIL unexpected event=%h",dut.system_i.commit_data);
                    endcase
                end
            end
        end
    end
endmodule
