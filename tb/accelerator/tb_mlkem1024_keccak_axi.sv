`timescale 1ns/1ps

// Every firmware/input write and result read travels through the AXI slave.
// Hierarchical observations count real CPU/HLS events; none drive the DUT.
module tb_mlkem1024_keccak_axi;
    parameter FIRMWARE_INIT_FILE="ps_kat.mem";
    parameter INPUT_FIXTURE_FILE="board_input.mem";
    parameter EXPECTED_FIXTURE_FILE="board_expected.mem";
    localparam [17:0] CONTROL=18'h20008, STATUS=18'h2000c, TRAP=18'h20010;
    localparam [31:0] KATR=32'h4b415452, KATP=32'h4b415450, KATF=32'h4b415446;
    localparam integer MAX_WORDS=16384, TIMEOUT_CYCLES=30000000;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg [17:0] awaddr=0, araddr=0;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=0;
    reg awvalid=0, wvalid=0, bready=0, arvalid=0, rready=0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    wire [3:0] led;
    mlkem1024_keccak_axi #(.FIRMWARE_INIT_FILE(FIRMWARE_INIT_FILE)) dut (
        .s_axi_aclk(clk),.s_axi_aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.led(led)
    );

    integer transactions=0, stalled_responses=0, protocol_checks=0;
    reg previous_b_stall=0, previous_r_stall=0;
    reg [1:0] previous_bresp=0, previous_rresp=0;
    reg [31:0] previous_rdata=0;
    always @(posedge clk) begin
        if (!resetn) begin previous_b_stall=0; previous_r_stall=0; end
        else begin
            if (previous_b_stall && (bvalid!==1 || bresp!==previous_bresp))
                $fatal(1,"AXI_KAT_FAIL unstable B response");
            if (previous_r_stall && (rvalid!==1 || rresp!==previous_rresp || rdata!==previous_rdata))
                $fatal(1,"AXI_KAT_FAIL unstable R response");
            if ((bvalid || rvalid) && (awready || wready || arready))
                $fatal(1,"AXI_KAT_FAIL more than one outstanding transaction");
            previous_b_stall=bvalid && !bready; previous_bresp=bresp;
            previous_r_stall=rvalid && !rready; previous_rresp=rresp; previous_rdata=rdata;
        end
    end

    task automatic axi_write(input [17:0] addr, input [31:0] value,
        input [3:0] strb, input integer aw_delay, input integer w_delay,
        input integer stalls, input [1:0] expected_resp);
        integer elapsed, guard;
        reg aw_done, w_done;
        begin
            @(negedge clk);
            awaddr=addr; wdata=value; wstrb=strb; bready=0;
            elapsed=0; aw_done=0; w_done=0;
            awvalid=(aw_delay==0); wvalid=(w_delay==0);
            while (!aw_done || !w_done) begin
                @(posedge clk);
                if (awvalid && awready) aw_done=1;
                if (wvalid && wready) w_done=1;
                @(negedge clk);
                elapsed=elapsed+1;
                if (elapsed>100) $fatal(1,"AXI_KAT_FAIL write handshake timeout addr=%h",addr);
                awvalid=!aw_done && elapsed>=aw_delay;
                wvalid=!w_done && elapsed>=w_delay;
            end
            guard=0;
            while (!bvalid) begin
                @(negedge clk); guard=guard+1;
                if (guard>100) $fatal(1,"AXI_KAT_FAIL missing B addr=%h",addr);
            end
            if (bresp!==expected_resp) $fatal(1,"AXI_KAT_FAIL BRESP addr=%h got=%b expected=%b",addr,bresp,expected_resp);
            repeat(stalls) @(negedge clk);
            if (bvalid!==1 || bresp!==expected_resp) $fatal(1,"AXI_KAT_FAIL B stall");
            bready=1;
            @(posedge clk); @(negedge clk); bready=0;
            transactions=transactions+1;
            if (stalls>0) stalled_responses=stalled_responses+1;
        end
    endtask

    task automatic axi_read(input [17:0] addr, input integer stalls,
        input [1:0] expected_resp, output reg [31:0] value);
        integer guard;
        reg accepted;
        begin
            @(negedge clk); araddr=addr; arvalid=1; rready=0; guard=0; accepted=0;
            while (!accepted) begin
                @(posedge clk); accepted=arready;
                @(negedge clk); guard=guard+1;
                if (guard>100) $fatal(1,"AXI_KAT_FAIL AR timeout addr=%h",addr);
            end
            arvalid=0; guard=0;
            while (!rvalid) begin
                @(negedge clk); guard=guard+1;
                if (guard>100) $fatal(1,"AXI_KAT_FAIL missing R addr=%h",addr);
            end
            value=rdata;
            if (rresp!==expected_resp) $fatal(1,"AXI_KAT_FAIL RRESP addr=%h got=%b expected=%b",addr,rresp,expected_resp);
            repeat(stalls) @(negedge clk);
            if (rvalid!==1 || rdata!==value || rresp!==expected_resp) $fatal(1,"AXI_KAT_FAIL R stall");
            rready=1;
            @(posedge clk); @(negedge clk); rready=0;
            transactions=transactions+1;
            if (stalls>0) stalled_responses=stalled_responses+1;
        end
    endtask

    task automatic expect_read(input [17:0] addr, input [31:0] wanted);
        reg [31:0] got;
        begin
            axi_read(addr,3,0,got);
            if (got!==wanted) $fatal(1,"AXI_KAT_FAIL read addr=%h got=%h expected=%h",addr,got,wanted);
            protocol_checks=protocol_checks+1;
        end
    endtask

    task automatic external_reset;
        begin
            @(negedge clk); resetn=0; awvalid=0; wvalid=0; arvalid=0; bready=0; rready=0;
            repeat(8) @(negedge clk);
            if (bvalid!==0 || rvalid!==0 || led!==0) $fatal(1,"AXI_KAT_FAIL external reset responses/LED");
            resetn=1;
            repeat(2) @(negedge clk);
        end
    endtask

    task automatic core_reset;
        begin
            axi_write(CONTROL,0,1,0,2,2,0);
            repeat(3) @(negedge clk);
            expect_read(CONTROL,0); expect_read(STATUS,0); expect_read(TRAP,0);
            expect_read(18'h20080,0); expect_read(18'h20084,0);
            expect_read(18'h20088,0); expect_read(18'h2008c,0);
            if (led!==0) $fatal(1,"AXI_KAT_FAIL reset LED gating");
        end
    endtask

    reg [31:0] input_fixture[0:MAX_WORDS-1], expected_fixture[0:MAX_WORDS-1];
    integer input_offset[0:2], expected_offset[0:2], input_size[0:2], output_size[0:2];
    integer expected_starts[0:2], expected_writes[0:2], expected_reads[0:2];
    integer input_words=0, expected_words=0;
    integer f, scan, i, j, pin, pout, case_index;
    reg [31:0] file_word, value, saved_instruction;
    reg [31:0] output_header[0:7], profiles[0:11], metrics[0:3];
    integer output_checks=0, total_starts=0, completed_cases=0, busy_aborts=0;

    task automatic load_case(input integer index);
        integer word_index, count_words;
        reg [31:0] payload_word;
        begin
            count_words=20+input_size[index]/4;
            for (word_index=0;word_index<count_words;word_index=word_index+1) begin
                if (word_index<8) begin
                    payload_word=input_fixture[word_index];
                    if (word_index==3) payload_word=1;
                    if (word_index==4) payload_word=count_words;
                end else begin
                    payload_word=input_fixture[input_offset[index]+word_index-8];
                    if (word_index==8) payload_word=0;
                end
                axi_write(18'h10000+4*word_index,payload_word,4'hf,
                          word_index%3,(word_index+1)%3,word_index%2,0);
            end
            expect_read(18'h10000,32'h3254414b);
            expect_read(18'h1000c,1); expect_read(18'h10010,count_words); expect_read(18'h10020,0);
        end
    endtask

    task automatic wait_status(input [31:0] wanted);
        integer polls;
        reg [31:0] observed;
        begin
            polls=0; observed=0;
            while (observed!==wanted) begin
                repeat(100) @(negedge clk);
                axi_read(STATUS,0,0,observed);
                if (observed===KATF && wanted!=KATF)
                    $fatal(1,"AXI_KAT_FAIL firmware error=%h",dut.system_i.debug_regs[1]);
                if (dut.trap) $fatal(1,"AXI_KAT_FAIL unexpected CPU trap");
                polls=polls+1;
                if (polls>TIMEOUT_CYCLES/100) $fatal(1,"AXI_KAT_FAIL job timeout");
            end
        end
    endtask

    // Independent evidence of starts/completions and of the API rdcycle pair.
    integer hls_starts=0, hls_dones=0, hash_calls=0, squeeze_calls=0, cycle_samples=0;
    reg previous_start=0, previous_done=0, measure_window=0, api_active=0;
    reg [31:0] api_begin=0, observed_cycles=0;
    always @(posedge clk) begin
        if (!dut.core_resetn) begin
            hls_starts=0; hls_dones=0; hash_calls=0; squeeze_calls=0; cycle_samples=0;
            previous_start=0; previous_done=0; measure_window=0; api_active=0;
            api_begin=0; observed_cycles=0;
        end else begin
            if (dut.system_i.local_write_commit && dut.system_i.commit_addr==32'h5000003c) begin
                if (dut.system_i.commit_data==32'h108) measure_window=1;
                if (dut.system_i.commit_data==32'h109) measure_window=0;
            end
            if (measure_window && dut.system_i.cpu.picorv32_core.cpu_state==8'b00100000 &&
                dut.system_i.cpu.picorv32_core.instr_rdcycle) begin
                if (cycle_samples==0) begin
                    api_begin=dut.system_i.cpu.picorv32_core.count_cycle[31:0]; api_active=1;
                end else if (cycle_samples==1) begin
                    observed_cycles=dut.system_i.cpu.picorv32_core.count_cycle[31:0]-api_begin; api_active=0;
                end else $fatal(1,"AXI_KAT_FAIL extra measured rdcycle");
                cycle_samples=cycle_samples+1;
            end
            if (dut.system_i.adapter_i.hls_i.ap_start && !previous_start) begin
                if (!api_active) $fatal(1,"AXI_KAT_FAIL HLS start outside measured API");
                hls_starts=hls_starts+1;
                case (dut.system_i.adapter_i.command_shadow)
                    0: hash_calls=hash_calls+1;
                    1: squeeze_calls=squeeze_calls+1;
                    default: $fatal(1,"AXI_KAT_FAIL unexpected HLS command");
                endcase
            end
            if (dut.system_i.adapter_i.hls_i.ap_done && !previous_done) hls_dones=hls_dones+1;
            previous_start=dut.system_i.adapter_i.hls_i.ap_start;
            previous_done=dut.system_i.adapter_i.hls_i.ap_done;
            if (dut.system_i.adapter_i.error) $fatal(1,"AXI_KAT_FAIL adapter error");
        end
    end

    initial begin #1200000000; $fatal(1,"AXI_KAT_FAIL global timeout"); end
    initial begin
        expected_starts[0]=26; expected_starts[1]=27; expected_starts[2]=32;
        expected_writes[0]=1969; expected_writes[1]=2037; expected_writes[2]=2697;
        expected_reads[0]=3648; expected_reads[1]=3732; expected_reads[2]=4168;
        f=$fopen(INPUT_FIXTURE_FILE,"r");
        if (!f) $fatal(1,"AXI_KAT_FAIL missing input fixture");
        while (!$feof(f)) begin
            scan=$fscanf(f,"%h",file_word);
            if (scan==1) begin
                if (input_words>=MAX_WORDS || (^file_word)===1'bx) $fatal(1,"AXI_KAT_FAIL invalid input fixture");
                input_fixture[input_words]=file_word; input_words=input_words+1;
            end else if (!$feof(f)) $fatal(1,"AXI_KAT_FAIL malformed input fixture");
        end
        $fclose(f);
        f=$fopen(EXPECTED_FIXTURE_FILE,"r");
        if (!f) $fatal(1,"AXI_KAT_FAIL missing expected fixture");
        while (!$feof(f)) begin
            scan=$fscanf(f,"%h",file_word);
            if (scan==1) begin
                if (expected_words>=MAX_WORDS || (^file_word)===1'bx) $fatal(1,"AXI_KAT_FAIL invalid expected fixture");
                expected_fixture[expected_words]=file_word; expected_words=expected_words+1;
            end else if (!$feof(f)) $fatal(1,"AXI_KAT_FAIL malformed expected fixture");
        end
        $fclose(f);
        if (input_words<8 || expected_words<8 || input_fixture[0]!==32'h3254414b ||
            input_fixture[1]!==1 || input_fixture[2]!==1024 || input_fixture[3]!==3 ||
            input_fixture[4]!==input_words || expected_fixture[4]!==expected_words)
            $fatal(1,"AXI_KAT_FAIL fixture header");
        for (i=0;i<8;i=i+1)
            if (i!=4 && input_fixture[i]!==expected_fixture[i]) $fatal(1,"AXI_KAT_FAIL mismatched fixture header");
        pin=8; pout=8;
        for (i=0;i<3;i=i+1) begin
            if (pin+12>input_words || pout+12>expected_words) $fatal(1,"AXI_KAT_FAIL truncated metadata");
            input_offset[i]=pin; expected_offset[i]=pout;
            for (j=0;j<11;j=j+1)
                if (input_fixture[pin+j]!==expected_fixture[pout+j]) $fatal(1,"AXI_KAT_FAIL fixture metadata mismatch");
            if (input_fixture[pin]!==i || input_fixture[pin+5]!==i+1 || input_fixture[pin+11]!==0 ||
                expected_fixture[pout+11]!==0) $fatal(1,"AXI_KAT_FAIL subset identity/return");
            for (j=6;j<11;j=j+1)
                if (input_fixture[pin+j]>4096 || input_fixture[pin+j]%4!=0) $fatal(1,"AXI_KAT_FAIL fixture lengths");
            input_size[i]=input_fixture[pin+6]+input_fixture[pin+7]+input_fixture[pin+8];
            output_size[i]=input_fixture[pin+9]+input_fixture[pin+10];
            pin=pin+12+input_size[i]/4; pout=pout+12+output_size[i]/4;
            if (pin>input_words || pout>expected_words) $fatal(1,"AXI_KAT_FAIL truncated payload");
        end
        if (pin!=input_words || pout!=expected_words) $fatal(1,"AXI_KAT_FAIL trailing fixture data");

        external_reset();
        expect_read(18'h20000,32'h4b344158); expect_read(18'h20004,1);
        expect_read(18'h20014,100000000); expect_read(18'h20018,131072); expect_read(18'h2001c,0);
        expect_read(CONTROL,0); expect_read(STATUS,0);
        axi_write(18'h16000,32'h12345678,4'hf,0,7,9,0);
        expect_read(18'h16000,32'h12345678);
        axi_write(18'h16000,32'haabbccdd,4'b0101,7,0,7,0);
        expect_read(18'h16000,32'h12bb56dd);
        axi_write(18'h16000,32'hffffffff,0,0,0,1,0);
        expect_read(18'h16000,32'h12bb56dd);
        axi_write(18'h1fffc,32'hcafef00d,4'hf,0,0,0,0);
        expect_read(18'h1fffc,32'hcafef00d);
        axi_write(CONTROL,1,4'b0010,4,0,3,0); expect_read(CONTROL,0);
        axi_write(18'h16001,0,4'hf,0,3,3,2); expect_read(18'h16000,32'h12bb56dd);
        axi_write(18'h20000,0,4'hf,3,0,3,2); axi_write(18'h20040,0,4'hf,0,0,3,2);
        axi_write(18'h3fffc,0,4'hf,0,3,3,2);
        axi_read(18'h16002,5,2,value); axi_read(18'h20020,5,2,value); axi_read(18'h3fffc,5,2,value);

        // AW and AR asserted together: finish the write, then accept the read.
        @(negedge clk); awaddr=18'h16004; awvalid=1; wdata=32'h87654321; wstrb=15; wvalid=1;
        araddr=18'h16004; arvalid=1;
        @(posedge clk);
        if (awready!==1 || wready!==1 || arready!==0) $fatal(1,"AXI_KAT_FAIL write/read arbitration");
        @(negedge clk); awvalid=0; wvalid=0;
        repeat(5) begin @(negedge clk); if (arready!==0 || bvalid!==1) $fatal(1,"AXI_KAT_FAIL read overtook write"); end
        bready=1; @(posedge clk); @(negedge clk); bready=0;
        @(posedge clk); if (arready!==1) $fatal(1,"AXI_KAT_FAIL read starved after write");
        @(negedge clk); arvalid=0;
        repeat(3) @(negedge clk);
        if (rvalid!==1 || rresp!==0 || rdata!==32'h87654321) $fatal(1,"AXI_KAT_FAIL arbitration readback");
        rready=1; @(posedge clk); @(negedge clk); rready=0;

        // Reset must discard either partial write, without changing RAM.
        @(negedge clk); awaddr=18'h16000; awvalid=1;
        @(posedge clk); if (!awready) $fatal(1,"AXI_KAT_FAIL partial AW not accepted");
        @(negedge clk); awvalid=0;
        external_reset(); expect_read(18'h16000,32'h12bb56dd);
        @(negedge clk); wdata=0; wstrb=15; wvalid=1;
        @(posedge clk); if (!wready) $fatal(1,"AXI_KAT_FAIL partial W not accepted");
        @(negedge clk); wvalid=0;
        external_reset(); expect_read(18'h16000,32'h12bb56dd);

        // A genuine illegal CPU instruction exercises TRAP and RAM ownership.
        axi_read(0,0,0,saved_instruction);
        axi_write(0,32'hffffffff,15,0,0,0,0); axi_write(CONTROL,1,1,0,0,0,0);
        i=0; value=0;
        while (value!==1) begin
            axi_read(TRAP,0,0,value); i=i+1;
            if (i>1000) $fatal(1,"AXI_KAT_FAIL no illegal-instruction trap");
        end
        expect_read(0,32'hffffffff);
        axi_write(18'h16000,0,15,0,0,3,2);
        if (led!==4'b1010) $fatal(1,"AXI_KAT_FAIL trap LED");
        core_reset(); axi_write(0,saved_instruction,15,0,0,0,0);
        expect_read(0,saved_instruction); expect_read(18'h16000,32'h12bb56dd);

        // A rejected transport clears stale output and allows postmortem reads.
        load_case(0); axi_write(18'h10000,0,15,0,0,0,0);
        axi_write(CONTROL,1,1,0,0,0,0); wait_status(KATF);
        expect_read(18'h20044,2); expect_read(18'h12000,0); expect_read(18'h20080,0);
        if (led!==4'b0010) $fatal(1,"AXI_KAT_FAIL invalid-input LED");
        core_reset();

        // Abort one active hardware operation, then reuse the same RAM image.
        load_case(0); axi_write(CONTROL,1,1,0,0,0,0);
        axi_write(18'h16000,0,15,0,3,3,2); axi_read(18'h16000,5,2,value);
        axi_write(CONTROL,0,4'b0010,3,0,3,0); expect_read(CONTROL,1);
        wait(dut.system_i.adapter_i.hls_i.ap_start===1'b1);
        if (!dut.system_i.adapter_i.busy) $fatal(1,"AXI_KAT_FAIL abort missed busy accelerator");
        core_reset(); busy_aborts=busy_aborts+1;
        expect_read(18'h10000,32'h3254414b); expect_read(18'h16000,32'h12bb56dd);
        $display("AXI_PROTOCOL_PASS checks=%0d stalled_responses=%0d busy_aborts=%0d",protocol_checks,stalled_responses,busy_aborts);

        for (case_index=0;case_index<3;case_index=case_index+1) begin
            load_case(case_index); axi_write(CONTROL,1,1,case_index%3,(case_index+1)%3,3,0);
            wait_status(KATP);
            if (led!==4'b0001) $fatal(1,"AXI_KAT_FAIL completion LED case=%0d",case_index);
            expect_read(TRAP,0); expect_read(CONTROL,1);
            axi_write(18'h16000,0,15,0,0,3,2);
            for (j=0;j<8;j=j+1) axi_read(18'h12000+4*j,j%3,0,output_header[j]);
            for (j=0;j<12;j=j+1) axi_read(18'h20040+4*j,j%3,0,profiles[j]);
            for (j=0;j<4;j=j+1) axi_read(18'h20080+4*j,j%3,0,metrics[j]);
            pin=input_offset[case_index]; pout=expected_offset[case_index];
            if (output_header[0]!==32'h4b34524f || output_header[1]!==1 ||
                output_header[2]!==input_fixture[pin+5] || output_header[3]!==expected_fixture[pout+11] ||
                output_header[4]!==input_fixture[pin+9] || output_header[5]!==input_fixture[pin+10] ||
                output_header[6]!==observed_cycles || output_header[6]<=output_header[7] || output_header[7]==0 ||
                profiles[0]!==KATP || profiles[1]!==0 || profiles[2]!==0 || profiles[3]!==output_header[6] ||
                profiles[4]!==output_header[2] || profiles[5]!==input_fixture[pin+1] ||
                profiles[6]!==input_fixture[pin+4] || profiles[7]!==input_size[case_index] ||
                profiles[8]!==output_header[7] || profiles[9]!==output_header[3])
                $fatal(1,"AXI_KAT_FAIL output/profile header case=%0d cycles=%0d observed=%0d",case_index,output_header[6],observed_cycles);
            if (cycle_samples!=2 || metrics[0]!==expected_starts[case_index] || metrics[0]!==hls_starts ||
                hls_starts!=hls_dones || hash_calls!=26+case_index || squeeze_calls!=((case_index==2)?4:0) ||
                metrics[1]==0 || metrics[1]>=output_header[6] || metrics[2]!==expected_writes[case_index] ||
                metrics[3]!==expected_reads[case_index] || dut.system_i.adapter_i.busy)
                $fatal(1,"AXI_KAT_FAIL hardware counters case=%0d starts=%0d done=%0d busy=%0d writes=%0d reads=%0d",
                       case_index,hls_starts,hls_dones,metrics[1],metrics[2],metrics[3]);
            for (j=0;j<output_size[case_index]/4;j=j+1) begin
                axi_read(18'h12020+4*j,j%3,0,value);
                if (value!==expected_fixture[pout+12+j])
                    $fatal(1,"AXI_KAT_FAIL output case=%0d byte=%0d got=%h expected=%h",case_index,j*4,value,expected_fixture[pout+12+j]);
                output_checks=output_checks+4;
            end
            total_starts=total_starts+hls_starts; completed_cases=completed_cases+1;
            $display("AXI_KAT_ROW case=%0d op=%0d return=%0d cycles=%0d empty=%0d starts=%0d busy=%0d writes=%0d reads=%0d input_bytes=%0d output_bytes=%0d",
                case_index,output_header[2],$signed(output_header[3]),output_header[6],output_header[7],
                metrics[0],metrics[1],metrics[2],metrics[3],input_size[case_index],output_size[case_index]);
            core_reset();
        end
        if (completed_cases!=3 || total_starts!=85 || output_checks!=6368 || busy_aborts!=1)
            $fatal(1,"AXI_KAT_FAIL incomplete evidence");
        $display("AXI_KAT_PASS cases=3 starts=85 output_bytes=%0d transactions=%0d stalled_responses=%0d busy_aborts=1",output_checks,transactions,stalled_responses);
        $finish;
    end
endmodule
