`timescale 1ns/1ps
module tb_mlkem512_cpu_smoke;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    wire trap;
    wire [31:0] status;
    wire [383:0] profile_words;
    mlkem512_accel_system #(.FIRMWARE_INIT_FILE("smoke.mem"), .RAM_ADDR_BITS(14),
        .CPU_ENABLE_MUL(1), .CPU_ENABLE_FAST_MUL(1), .CPU_ENABLE_DIV(1)) dut (
        .clk(clk),.resetn(resetn),.trap(trap),.status_out(status),.profile_words(profile_words));
    reg [15:0] expected0[0:255], expected1[0:255], expected2[0:255];
    reg [31:0] wanted;
    integer checked=0, ticks=0, c, j;
    initial begin
        $readmemh("case_000_expected.mem",expected0);
        $readmemh("case_001_expected.mem",expected1);
        $readmemh("case_002_expected.mem",expected2);
        repeat(10) @(negedge clk);
        resetn=1;
    end
    always @(posedge clk) if(resetn) begin
        ticks=ticks+1;
        if(trap || status===32'h41434346) $fatal(1,"CPU_ACCEL_SMOKE_FAIL trap/status ticks=%0d",ticks);
        if(ticks>2000000) $fatal(1,"CPU_ACCEL_SMOKE_FAIL timeout");
        if(dut.local_write_commit && dut.commit_addr==32'h5000003c) begin
            c=checked/128; j=checked%128;
            if(checked>=384 || dut.debug_regs[1]!==c || dut.debug_regs[2]!==j || dut.commit_data!==checked+1)
                $fatal(1,"CPU_ACCEL_SMOKE_FAIL output order checked=%0d",checked);
            case(c)
                0: wanted={expected0[2*j+1],expected0[2*j]};
                1: wanted={expected1[2*j+1],expected1[2*j]};
                2: wanted={expected2[2*j+1],expected2[2*j]};
            endcase
            if(dut.debug_regs[3]!==wanted) $fatal(1,"CPU_ACCEL_SMOKE_FAIL case=%0d word=%0d got=%h expected=%h",c,j,dut.debug_regs[3],wanted);
            if(j==0) begin
                if(dut.debug_regs[5]!==136 || dut.debug_regs[6]!==640*(c+1) || dut.debug_regs[7]!==128*(c+1) || dut.debug_regs[4]<=136)
                    $fatal(1,"CPU_ACCEL_SMOKE_FAIL metrics case=%0d",c);
                $display("CPU_ACCEL_CASE_PASS case=%0d call_cycles=%0d core_cycles=%0d cumulative_loads=%0d cumulative_reads=%0d",c,dut.debug_regs[4],dut.debug_regs[5],dut.debug_regs[6],dut.debug_regs[7]);
            end
            checked=checked+1;
        end
        if(status===32'h41434350) begin
            if(checked!=384) $fatal(1,"CPU_ACCEL_SMOKE_FAIL incomplete");
            $display("CPU_ACCEL_SMOKE_PASS cases=3 coefficients=768 cpu=rv32im_fast total_cycles=%0d",ticks);
            $finish;
        end
    end
endmodule
