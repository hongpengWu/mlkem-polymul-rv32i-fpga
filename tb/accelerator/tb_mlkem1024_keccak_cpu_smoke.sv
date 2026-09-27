`timescale 1ns/1ps
// Ten local FIPS 202 component calls from real RV32IM firmware. Expectations
// originate from Python hashlib and are present only in this testbench.
module tb_mlkem1024_keccak_cpu_smoke;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    wire trap;
    wire [31:0] status;
    wire [383:0] profile_words;
    mlkem1024_keccak_system #(.FIRMWARE_INIT_FILE("smoke.mem"), .RAM_ADDR_BITS(15),
        .CPU_ENABLE_MUL(1), .CPU_ENABLE_FAST_MUL(1), .CPU_ENABLE_DIV(1)) dut (
        .clk(clk), .resetn(resetn), .trap(trap), .status_out(status),
        .profile_words(profile_words));
    reg [31:0] expected [0:215];
    // Per call: output offset/count, return, cumulative buffer writes/reads,
    // output/input byte lengths, packed mode/command.
    reg [31:0] metadata [0:79];
    integer ticks=0, completed=0, checked=0, in_call=0;
    integer hls_starts=0, hls_dones=0, base;
    reg previous_start=0, previous_done=0;
    reg [31:0] previous_busy=0;
    initial begin
        $readmemh("expected.mem", expected);
        $readmemh("meta.mem", metadata);
        repeat(10) @(negedge clk);
        resetn=1;
    end
    always @(posedge clk) if (resetn) begin
        ticks=ticks+1;
        if (dut.adapter_i.hls_i.ap_start && !previous_start) hls_starts=hls_starts+1;
        if (dut.adapter_i.hls_i.ap_done && !previous_done) hls_dones=hls_dones+1;
        previous_start=dut.adapter_i.hls_i.ap_start;
        previous_done=dut.adapter_i.hls_i.ap_done;
        if (trap || status===32'h4b435046)
            $fatal(1,"KECCAK_CPU_SMOKE_FAIL trap/status cycles=%0d result=%0d",ticks,$signed(dut.debug_regs[5]));
        if (ticks>10000000) $fatal(1,"KECCAK_CPU_SMOKE_FAIL timeout");
        if (dut.local_write_commit && dut.commit_addr==32'h5000003c) begin
            if (completed>=10 || checked>=216)
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL excess output");
            base=8*completed;
            if (dut.debug_regs[1]!==completed || dut.debug_regs[2]!==in_call ||
                dut.commit_data!==checked+1 || in_call>=metadata[base+1] ||
                checked!=metadata[base]+in_call)
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL output order call=%0d word=%0d",completed,in_call);
            if (dut.debug_regs[3]!==expected[checked])
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL output call=%0d word=%0d got=%h expected=%h",completed,in_call,dut.debug_regs[3],expected[checked]);
            checked=checked+1;
            in_call=in_call+1;
        end
        if (dut.local_write_commit && dut.commit_addr==32'h50000038) begin
            if (completed>=10) $fatal(1,"KECCAK_CPU_SMOKE_FAIL excess call");
            base=8*completed;
            if (dut.commit_data!==completed+1 || dut.debug_regs[1]!==completed ||
                in_call!=metadata[base+1] || dut.debug_regs[5]!==metadata[base+2] ||
                dut.debug_regs[11]!==metadata[base+5] || dut.debug_regs[12]!==1)
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL call metadata/context call=%0d return=%0d expected=%0d",completed,$signed(dut.debug_regs[5]),$signed(metadata[base+2]));
            if (dut.debug_regs[6]!==completed+1 ||
                dut.debug_regs[8]!==metadata[base+3] || dut.debug_regs[9]!==metadata[base+4] ||
                dut.debug_regs[7]<=previous_busy ||
                dut.debug_regs[4] <= (dut.debug_regs[7]-previous_busy) ||
                dut.debug_regs[10][2:0]!==3'b010 ||
                hls_starts!=completed+1 || hls_dones!=completed+1)
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL hardware metrics call=%0d starts=%0d/%0d dones=%0d busy=%0d writes=%0d/%0d reads=%0d/%0d flags=%h",completed,hls_starts,dut.debug_regs[6],hls_dones,dut.debug_regs[7],dut.debug_regs[8],metadata[base+3],dut.debug_regs[9],metadata[base+4],dut.debug_regs[10]);
            $display("KECCAK_CPU_CALL_PASS call=%0d mode=%0d command=%0d input=%0d output=%0d return=%0d cpu_cycles=%0d hardware_busy=%0d cumulative_writes=%0d cumulative_reads=%0d",completed,metadata[base+7]&255,metadata[base+7]>>8,metadata[base+6],metadata[base+5],$signed(dut.debug_regs[5]),dut.debug_regs[4],dut.debug_regs[7]-previous_busy,dut.debug_regs[8],dut.debug_regs[9]);
            previous_busy=dut.debug_regs[7];
            completed=completed+1;
            in_call=0;
        end
        if (status===32'h4b435050) begin
            if (completed!=10 || checked!=216 || hls_starts!=10 || hls_dones!=10)
                $fatal(1,"KECCAK_CPU_SMOKE_FAIL incomplete");
            $display("KECCAK_CPU_SMOKE_PASS calls=10 words=216 hls_starts=10 hls_dones=10 cpu=rv32im_fast total_cycles=%0d",ticks);
            $finish;
        end
    end
endmodule
