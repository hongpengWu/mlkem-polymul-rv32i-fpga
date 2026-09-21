`timescale 1ns/1ps
module tb_software_baseline #(parameter COMPUTE_AUDIT=0);
  reg clk=0, resetn=0;
  always #5 clk=~clk;
  wire trap;
  wire [31:0] status;
  integer a[0:255],b[0:255],expected[0:255];
  longint signed acc[0:255];
  integer i,j,k,words=0;
  reg [31:0] golden;
  longint unsigned elapsed=0, function_start=0, function_end=0;
  reg function_seen=0, function_returned=0;
  reg [31:0] previous_pc=32'hffffffff;
  // Passive PC boundaries for the archived software_o2 ELF. The audit runner
  // checks its image hash and disassembly before using these addresses.
  always @(negedge clk) if(resetn && COMPUTE_AUDIT) begin
    elapsed=elapsed+1;
    if(dut.cpu.picorv32_core.reg_pc != previous_pc) begin
      if(dut.cpu.picorv32_core.reg_pc==32'h3ac) begin
        if(function_seen) $fatal(1,"Unexpected repeated PolyMul entry");
        function_seen=1; function_start=elapsed;
        $display("SOFTWARE COMPUTE BEGIN pc=000003ac cycle=%0d",elapsed);
      end
      if(function_seen && !function_returned && dut.cpu.picorv32_core.reg_pc==32'hd4) begin
        function_returned=1; function_end=elapsed;
        $display("SOFTWARE COMPUTE END pc=000000d4 cycle=%0d compute_cycles=%0d",elapsed,function_end-function_start);
      end
      previous_pc=dut.cpu.picorv32_core.reg_pc;
    end
  end
  mlkem_polymul_rv32i_profile_top #(.FIRMWARE_INIT_FILE("software_o2.mem")) dut(
    .clk(clk),.resetn(resetn),.trap(trap),.status_out(status));
  always @(posedge clk) if(resetn) begin
    if(trap) $fatal(1,"Software CPU trap");
    if(dut.ip_awvalid || dut.ip_arvalid) $fatal(1,"Software accessed accelerator");
    if(dut.local_write_commit && dut.commit_addr==32'h50000014) begin
      if(words>=128) $fatal(1,"Too many output words");
      golden={expected[2*words+1][15:0],expected[2*words][15:0]};
      if(dut.commit_data !== golden) $fatal(1,"Oracle mismatch word=%0d got=%h expected=%h",words,dut.commit_data,golden);
      words=words+1;
    end
  end
  initial begin
    for(i=0;i<256;i=i+1) begin
      a[i]=(17*i*i+31*i+7)%3329;
      b[i]=(29*i*i+11*i+19)%3329;
      acc[i]=0;
    end
    for(i=0;i<256;i=i+1) for(j=0;j<256;j=j+1) begin
      k=i+j;
      if(k<256) acc[k]=acc[k]+a[i]*b[j];
      else acc[k-256]=acc[k-256]-a[i]*b[j];
    end
    for(i=0;i<256;i=i+1) begin
      expected[i]=acc[i]%3329;
      if(expected[i]<0) expected[i]=expected[i]+3329;
    end
    repeat(10) @(negedge clk);
    resetn=1;
    wait(status==32'h600d600d || status[31:16]==16'hdead);
    @(negedge clk);
    if(status!==32'h600d600d || words!=128 || dut.debug_regs[1]!==0) $fatal(1,"Software check failed");
    $display("SOFTWARE BASELINE PASS cycles=%0d rdcycle=%0d words=%0d",dut.debug_regs[2],dut.debug_regs[3],words);
    if(COMPUTE_AUDIT) begin
      if(!function_seen || !function_returned || function_end<=function_start)
        $fatal(1,"Compute boundaries missing");
      if(function_end-function_start>dut.debug_regs[2])
        $fatal(1,"Function window exceeds surrounding rdcycle window");
      $display("SOFTWARE COMPUTE AUDIT PASS compute_cycles=%0d rdcycle_window=%0d boundary_difference=%0d words=%0d errors=%0d",function_end-function_start,dut.debug_regs[2],dut.debug_regs[2]-(function_end-function_start),words,dut.debug_regs[1]);
    end
    $finish;
  end
  initial begin #200000000; $fatal(1,"Software timeout"); end
endmodule
