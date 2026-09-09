`timescale 1ns/1ps
`default_nettype none
module tb_blind_printer_core;
    reg clk=0;
    always #5 clk=~clk; // 100 MHz reference
    reg rst_n=0, estop=0, keyword_valid=0, text_valid=0;
    reg [2:0] keyword_id=0;
    reg [7:0] text_ascii=0;
    reg text_complete=0, text_error=0, cell_ready=0;
    reg print_done=0, print_error=0;
    wire keyword_ready, text_ready, cell_valid, cell_newline;
    wire [5:0] cell_bits;
    wire [2:0] state, prompt_id;
    wire capture_req, start_print, job_clear, prompt_valid, error_latched;
    wire unsupported;
    wire [7:0] unsupported_ascii;
    wire x_step, x_dir, y_step, y_dir, punch_enable, motion_enable;
    wire kws_pcm_ready, kws_valid, kws_implemented;
    wire [2:0] kws_id;
    wire zh_ready, zh_valid, zh_implemented;
    wire [5:0] zh_bits;
    blind_printer_core dut (.*);
    kws_model_slot kws (
        .clk(clk), .rst_n(rst_n), .pcm_valid(1'b1), .pcm_sample(16'h1234),
        .pcm_ready(kws_pcm_ready), .keyword_valid(kws_valid),
        .keyword_id(kws_id), .keyword_ready(1'b1), .implemented(kws_implemented)
    );
    chinese_braille_slot zh (
        .clk(clk), .rst_n(rst_n), .clear(1'b0), .unicode_valid(1'b1),
        .unicode_scalar(21'h4e2d), .unicode_ready(zh_ready), .cell_valid(zh_valid),
        .cell_bits(zh_bits), .cell_ready(1'b1), .implemented(zh_implemented)
    );

    task automatic tick;
        @(posedge clk); #1;
    endtask
    task automatic check_state(input [2:0] expected);
        if (state !== expected) $fatal(1,"state: got %0d expected %0d",state,expected);
    endtask
    task automatic reset_core;
        @(negedge clk);
        rst_n=0; estop=0; keyword_valid=0; text_valid=0;
        text_complete=0; text_error=0; cell_ready=0; print_done=0; print_error=0;
        tick(); tick();
        @(negedge clk); rst_n=1;
        tick(); check_state(0);
    endtask
    task automatic keyword(input [2:0] id);
        @(negedge clk); keyword_id=id; keyword_valid=1;
        tick();
        @(negedge clk); keyword_valid=0;
    endtask
    task automatic byte_in(input [7:0] value);
        integer waits;
        begin
            @(negedge clk); text_ascii=value; text_valid=1; waits=0;
            while (!text_ready && waits < 20) begin
                @(negedge clk); waits=waits+1;
            end
            if (!text_ready) $fatal(1,"input stalled for byte %h",value);
            tick();
            @(negedge clk); text_valid=0;
        end
    endtask
    task automatic event_out(input [5:0] expected, input newline);
        integer waits;
        begin
            waits=0;
            while (!cell_valid && waits < 20) begin tick(); waits=waits+1; end
            if (!cell_valid) $fatal(1,"missing cell %h",expected);
            if (cell_bits !== expected || cell_newline !== newline)
                $fatal(1,"event got %h/%b expected %h/%b",cell_bits,cell_newline,expected,newline);
            @(negedge clk); cell_ready=1;
            tick();
            @(negedge clk); cell_ready=0;
        end
    endtask
    task automatic end_text;
        @(negedge clk); text_complete=1;
        tick();
        @(negedge clk); text_complete=0;
    endtask
    task automatic start_capture;
        keyword(1); check_state(1);
        if (!prompt_valid || prompt_id != 1) $fatal(1,"missing place-book prompt");
        keyword(2); check_state(2);
        if (!capture_req) $fatal(1,"missing capture request");
    endtask

    always @(posedge clk) begin
        #2;
        if ({x_step,x_dir,y_step,y_dir,punch_enable,motion_enable} !== 6'b0)
            $fatal(1,"reference core must never actuate hardware");
        if ({kws_pcm_ready,kws_valid,kws_implemented,kws_id} !== 6'b0 ||
            {zh_ready,zh_valid,zh_implemented,zh_bits} !== 9'b0)
            $fatal(1,"unimplemented slots must not accept input or predict output");
    end

    initial begin
        reset_core();
        keyword(2); check_state(0); // wrong-state command is ignored
        start_capture();
        byte_in("A");
        repeat (4) begin
            tick();
            if (!cell_valid || cell_bits !== 6'h20 || cell_newline || text_ready)
                $fatal(1,"capital prefix/backpressure stability failure");
        end
        event_out(6'h20,0); event_out(6'h01,0);
        byte_in(" "); event_out(0,0);
        byte_in("1"); event_out(6'h3c,0); event_out(6'h01,0);
        byte_in("2"); event_out(6'h03,0);
        byte_in("a"); event_out(6'h30,0); event_out(6'h01,0);
        byte_in("0"); event_out(6'h3c,0); event_out(6'h1a,0);
        byte_in("B"); event_out(6'h30,0); event_out(6'h20,0); event_out(6'h03,0);
        byte_in(8'h0a); event_out(0,1);
        byte_in("z");
        end_text(); check_state(2); // end-of-text waits for stalled output
        repeat(3) tick(); check_state(2);
        event_out(6'h35,0);
        tick(); check_state(3);
        keyword(3); check_state(4);
        if (!start_print) $fatal(1,"missing start-print pulse");
        repeat(4) tick(); check_state(4); // converting cells is NOT print completion
        @(negedge clk); print_done=1;
        tick(); check_state(5);
        @(negedge clk); print_done=0;
        keyword(1); check_state(1); // next job
        keyword(4); check_state(0);

        // Cancel flushes stalled cells and numeric mode, allowing a clean job.
        start_capture(); byte_in("1");
        keyword(4); check_state(0);
        if (cell_valid) $fatal(1,"cancel did not flush cells");
        start_capture(); byte_in("a"); event_out(6'h01,0);
        keyword(4); check_state(0);

        // No silent character dropping: unsupported ASCII latches an error.
        start_capture(); byte_in(8'hff);
        if (!unsupported || unsupported_ascii !== 8'hff)
            $fatal(1,"unsupported character not reported");
        tick(); check_state(6);
        keyword(4); check_state(6);
        keyword(1); check_state(6);

        // Stop is latched; reset is the only recovery.
        reset_core(); start_capture(); keyword(5); check_state(6);
        keyword(4); check_state(6);
        reset_core();
        @(negedge clk); keyword_valid=1; keyword_id=4; estop=1;
        tick(); check_state(6); // emergency stop outranks CANCEL
        @(negedge clk); keyword_valid=0; estop=0;
        keyword(1); check_state(6);

        reset_core(); start_capture();
        @(negedge clk); text_complete=1; text_error=1;
        tick(); check_state(6); // OCR error outranks completion
        reset_core(); start_capture(); end_text(); tick(); check_state(6);
        reset_core(); start_capture(); byte_in(" "); event_out(0,0);
        end_text(); tick(); check_state(6); // whitespace-only jobs are rejected
        reset_core(); start_capture(); byte_in("a"); event_out(6'h01,0);
        end_text(); tick(); check_state(3);
        keyword(3); check_state(4);
        @(negedge clk); print_done=1; print_error=1;
        tick(); check_state(6); // print error outranks completion
        $display("PASS: workflow, fault precedence, stream conversion, backpressure, safe outputs, disabled slots");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"simulation timeout");
    end
endmodule
`default_nettype wire
