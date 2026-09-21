`timescale 1ns / 1ps

// Passive, simulation-only observer for the PicoRV32 AXI-Lite system.
// Scope: one outstanding read and one outstanding write; no burst support.
// Observe the CPU-facing AXI bus, not undocumented CPU-internal signals.
// latency = response handshake edge - first request-valid edge.
// active = latency + 1 (number of sampled edges, both ends included).
// gap = next request edge - previous response edge - 1.
// For each serial target stream: window = active_sum + gap_sum.
module mlkem_axi_profile_observer (
    input wire clk, resetn,
    input wire awvalid, awready,
    input wire [31:0] awaddr,
    input wire wvalid, wready,
    input wire [3:0] wstrb,
    input wire bvalid, bready,
    input wire arvalid, arready,
    input wire [31:0] araddr,
    input wire [2:0] arprot,
    input wire rvalid, rready
);
  localparam integer RAM_IFETCH=0, RAM_READ=1, RAM_WRITE=2,
      A_WRITE=3, B_WRITE=4, OUT_READ=5, CTRL_READ=6, CTRL_WRITE=7,
      OTHER_IP=8, DEBUG_IO=9, OTHER_IO=10, NK=11;

  longint unsigned cycle_no;
  integer txn_count [0:NK-1];
  longint unsigned latency_sum [0:NK-1];
  longint unsigned latency_min [0:NK-1];
  longint unsigned latency_max [0:NK-1];
  longint unsigned address_wait [0:NK-1];
  longint unsigned data_wait [0:NK-1];
  longint unsigned response_backpressure [0:NK-1];

  // Stream 0: all A/B writes in execution order. Stream 1: all OUT reads.
  integer stream_count [0:1];
  longint unsigned first_request [0:1], last_response [0:1];
  longint unsigned active_sum [0:1], gap_sum [0:1], gap_max [0:1];
  integer between_ifetch [0:1], between_ram_read [0:1], between_ram_write [0:1];
  reg [127:0] a_seen, b_seen, out_seen;

  reg wr_active, wr_aw_seen, wr_aw_done, wr_w_done, rd_active, rd_ar_done;
  reg [31:0] wr_addr, rd_addr;
  reg [2:0] rd_prot;
  reg [3:0] wr_strb;
  longint unsigned wr_start, rd_start, wr_aw_wait, wr_w_wait, wr_b_wait;
  longint unsigned rd_ar_wait, rd_r_wait;
  integer reset_i;

  function automatic integer kind_of(input reg is_write,
                                      input reg [31:0] addr,
                                      input reg [2:0] prot);
    if (addr < 32'h1000)
      kind_of = is_write ? RAM_WRITE : (prot[2] ? RAM_IFETCH : RAM_READ);
    else if (addr >= 32'h40001000 && addr < 32'h40001200 && is_write)
      kind_of = A_WRITE;
    else if (addr >= 32'h40001200 && addr < 32'h40001400 && is_write)
      kind_of = B_WRITE;
    else if (addr >= 32'h40001400 && addr < 32'h40001600 && !is_write)
      kind_of = OUT_READ;
    else if (addr == 32'h40000000)
      kind_of = is_write ? CTRL_WRITE : CTRL_READ;
    else if (addr[31:16] == 16'h4000) kind_of = OTHER_IP;
    else if (addr >= 32'h50000000 && addr < 32'h50000040) kind_of = DEBUG_IO;
    else kind_of = OTHER_IO;
  endfunction

  function automatic string kind_name(input integer kind);
    case (kind)
      RAM_IFETCH: kind_name="RAM_IFETCH";
      RAM_READ: kind_name="RAM_DATA_READ";
      RAM_WRITE: kind_name="RAM_DATA_WRITE";
      A_WRITE: kind_name="INPUT_A_WRITE";
      B_WRITE: kind_name="INPUT_B_WRITE";
      OUT_READ: kind_name="OUTPUT_READ";
      CTRL_READ: kind_name="CONTROL_READ";
      CTRL_WRITE: kind_name="CONTROL_WRITE";
      OTHER_IP: kind_name="OTHER_IP";
      DEBUG_IO: kind_name="DEBUG";
      default: kind_name="OTHER";
    endcase
  endfunction

  task automatic record_transaction(input integer kind,
      input reg [31:0] addr, input longint unsigned start_edge,
      input longint unsigned aw_ar_wait, w_wait, resp_wait);
    integer g, s, word_no;
    longint unsigned lat, gap;
    begin
      lat = cycle_no - start_edge;
      if (txn_count[kind] == 0 || lat < latency_min[kind]) latency_min[kind] = lat;
      if (lat > latency_max[kind]) latency_max[kind] = lat;
      txn_count[kind] = txn_count[kind] + 1;
      latency_sum[kind] = latency_sum[kind] + lat;
      address_wait[kind] = address_wait[kind] + aw_ar_wait;
      data_wait[kind] = data_wait[kind] + w_wait;
      response_backpressure[kind] = response_backpressure[kind] + resp_wait;

      // Supplemental counts between target transfers. These are not rdcycle
      // stage totals and do not include local loads before the first target.
      for (s=0; s<2; s=s+1)
        if (stream_count[s] > 0 && stream_count[s] < (s==0 ? 256 : 128)) begin
          if (kind==RAM_IFETCH) between_ifetch[s] = between_ifetch[s]+1;
          if (kind==RAM_READ) between_ram_read[s] = between_ram_read[s]+1;
          if (kind==RAM_WRITE) between_ram_write[s] = between_ram_write[s]+1;
        end

      g = -1;
      if (kind==A_WRITE || kind==B_WRITE) g=0;
      if (kind==OUT_READ) g=1;
      if (g >= 0) begin
        if (addr[1:0] != 0) $fatal(1,"AXI_OBSERVER: unaligned target word");
        if (g==0 && wr_strb != 4'hf)
          $fatal(1,"AXI_OBSERVER: profiling input is not a full 32-bit write");
        word_no = int'((addr & 32'h1ff) >> 2);
        if (kind==A_WRITE) a_seen[word_no]=1'b1;
        if (kind==B_WRITE) b_seen[word_no]=1'b1;
        if (kind==OUT_READ) out_seen[word_no]=1'b1;

        gap=0;
        if (stream_count[g]==0) first_request[g]=start_edge;
        else begin
          if (start_edge <= last_response[g])
            $fatal(1,"AXI_OBSERVER: target transactions overlap; serial accounting unsupported");
          gap=start_edge-last_response[g]-1;
          gap_sum[g]=gap_sum[g]+gap;
          if (gap>gap_max[g]) gap_max[g]=gap;
        end
        active_sum[g]=active_sum[g]+lat+1;
        last_response[g]=cycle_no;
        stream_count[g]=stream_count[g]+1;
        if (stream_count[g] <= 3)
          $display("AXI_SAMPLE stream=%0d addr=%08x first=%0d response=%0d latency=%0d gap=%0d",
                   g,addr,start_edge,cycle_no,lat,gap);
      end
    end
  endtask

  // Blocking assignments are intentional for this simulation monitor: all
  // request/handshake events on one sampled edge are processed in order.
  always @(posedge clk) begin
    if (!resetn) begin
      cycle_no=0;
      wr_active=0; wr_aw_seen=0; wr_aw_done=0; wr_w_done=0;
      rd_active=0; rd_ar_done=0;
      wr_addr=0; rd_addr=0; rd_prot=0; wr_strb=0;
      wr_start=0; rd_start=0;
      wr_aw_wait=0; wr_w_wait=0; wr_b_wait=0; rd_ar_wait=0; rd_r_wait=0;
      a_seen=0; b_seen=0; out_seen=0;
      for (reset_i=0; reset_i<NK; reset_i=reset_i+1) begin
        txn_count[reset_i]=0; latency_sum[reset_i]=0;
        latency_min[reset_i]=0; latency_max[reset_i]=0;
        address_wait[reset_i]=0; data_wait[reset_i]=0;
        response_backpressure[reset_i]=0;
      end
      for (reset_i=0; reset_i<2; reset_i=reset_i+1) begin
        stream_count[reset_i]=0; first_request[reset_i]=0; last_response[reset_i]=0;
        active_sum[reset_i]=0; gap_sum[reset_i]=0; gap_max[reset_i]=0;
        between_ifetch[reset_i]=0; between_ram_read[reset_i]=0; between_ram_write[reset_i]=0;
      end
    end else begin
      cycle_no=cycle_no+1;
      if (!wr_active && (awvalid || wvalid)) begin
        wr_active=1; wr_start=cycle_no;
        wr_aw_seen=0; wr_aw_done=0; wr_w_done=0;
        wr_aw_wait=0; wr_w_wait=0; wr_b_wait=0;
      end
      if (wr_active) begin
        if (awvalid) begin
          if (wr_aw_done) $fatal(1,"AXI_OBSERVER: more than one outstanding AW");
          if (wr_aw_seen && awaddr != wr_addr) $fatal(1,"AXI_OBSERVER: stalled AW changed address");
          wr_aw_seen=1; wr_addr=awaddr;
          if (awready) wr_aw_done=1;
          else wr_aw_wait=wr_aw_wait+1;
        end
        if (wvalid) begin
          if (wr_w_done) $fatal(1,"AXI_OBSERVER: more than one outstanding W");
          wr_strb=wstrb;
          if (wready) wr_w_done=1;
          else wr_w_wait=wr_w_wait+1;
        end
        if (bvalid && !bready) wr_b_wait=wr_b_wait+1;
      end
      if (bvalid && bready) begin
        if (!wr_active || !wr_aw_done || !wr_w_done)
          $fatal(1,"AXI_OBSERVER: B response without matched AW and W");
        record_transaction(kind_of(1'b1,wr_addr,3'b0), wr_addr,
                           wr_start,wr_aw_wait,wr_w_wait,wr_b_wait);
        wr_active=0;
      end

      if (!rd_active && arvalid) begin
        rd_active=1; rd_start=cycle_no; rd_ar_done=0;
        rd_addr=araddr; rd_prot=arprot; rd_ar_wait=0; rd_r_wait=0;
      end
      if (rd_active) begin
        if (arvalid) begin
          if (rd_ar_done) $fatal(1,"AXI_OBSERVER: more than one outstanding AR");
          if (araddr != rd_addr || arprot != rd_prot)
            $fatal(1,"AXI_OBSERVER: stalled AR changed address/protection");
          if (arready) rd_ar_done=1;
          else rd_ar_wait=rd_ar_wait+1;
        end
        if (rvalid && !rready) rd_r_wait=rd_r_wait+1;
      end
      if (rvalid && rready) begin
        if (!rd_active || !rd_ar_done) $fatal(1,"AXI_OBSERVER: R response without matched AR");
        record_transaction(kind_of(1'b0,rd_addr,rd_prot), rd_addr,
                           rd_start,rd_ar_wait,0,rd_r_wait);
        rd_active=0;
      end
    end
  end

  task automatic check_call(input integer expected_polls);
    begin
      if (txn_count[A_WRITE]!=128 || txn_count[B_WRITE]!=128 || txn_count[OUT_READ]!=128)
        $fatal(1,"AXI_OBSERVER count mismatch: A=%0d B=%0d OUT=%0d",
               txn_count[A_WRITE],txn_count[B_WRITE],txn_count[OUT_READ]);
      if (a_seen!={128{1'b1}} || b_seen!={128{1'b1}} || out_seen!={128{1'b1}})
        $fatal(1,"AXI_OBSERVER: not all 128 distinct words were accessed in each array");
      if (txn_count[CTRL_WRITE]!=1 || txn_count[CTRL_READ]!=expected_polls)
        $fatal(1,"AXI_OBSERVER control mismatch: writes=%0d reads=%0d expected_polls=%0d",
               txn_count[CTRL_WRITE],txn_count[CTRL_READ],expected_polls);
    end
  endtask

  task automatic report(input integer trial_number);
    integer k, g;
    longint unsigned window_edges;
    begin
      $display("AXI_OBSERVER trial=%0d scope=CPU-facing_AXI counts=completed_transactions",trial_number);
      for (k=0; k<NK; k=k+1)
        if (txn_count[k] != 0)
          $display("AXI_CLASS %s n=%0d latency_avg=%.3f min=%0d max=%0d address_stall=%0d w_stall=%0d response_backpressure=%0d",
                   kind_name(k),txn_count[k],real'(latency_sum[k])/real'(txn_count[k]),
                   latency_min[k],latency_max[k],address_wait[k],data_wait[k],response_backpressure[k]);
      for (g=0; g<2; g=g+1)
        if (stream_count[g] != 0) begin
          window_edges=last_response[g]-first_request[g]+1;
          if (window_edges != active_sum[g]+gap_sum[g])
            $fatal(1,"AXI_OBSERVER: stream window accounting mismatch");
          $display("AXI_STREAM stream=%0d n=%0d window=%0d active=%0d gaps=%0d gap_max=%0d between_ifetch=%0d between_ram_read=%0d between_ram_write=%0d",
                   g,stream_count[g],window_edges,active_sum[g],gap_sum[g],gap_max[g],
                   between_ifetch[g],between_ram_read[g],between_ram_write[g]);
        end
      $display("AXI_NOTE stream0=A/B_writes stream1=OUT_reads; active includes both boundary edges.");
      $display("AXI_NOTE stream windows exclude rdcycle-stage head/tail; gaps include other bus traffic and CPU/adapter time.");
      $display("AXI_NOTE channel stalls may overlap; do not sum them as independent time or claim all latency is removable.");
    end
  endtask
endmodule
