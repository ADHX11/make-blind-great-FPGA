`timescale 1ns/1ps
`default_nettype none
// Board-independent PL core; active board target: AFC03 / PH1A90SEG324.
// clk is the board adapter's PL clock (100 MHz target); reset must be safely
// synchronized/deasserted there. No package pins, PLL, UART, USB, I2S, UTF-8,
// camera controller, neural model, page buffer, layout or motor driver here.
// A future adapter must buffer the full page from cell_* before PRINT.
module blind_printer_core (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       estop,
    input  wire       keyword_valid,
    input  wire [2:0] keyword_id,
    output wire       keyword_ready,
    input  wire       text_valid,
    input  wire [7:0] text_ascii,
    output wire       text_ready,
    // Pulse after the last ASCII byte has been accepted. The core waits for
    // its pending cells to be consumed before declaring READY.
    input  wire       text_complete,
    input  wire       text_error,
    output wire       cell_valid,
    output wire [5:0] cell_bits,
    output wire       cell_newline,
    input  wire       cell_ready,
    input  wire       print_done, // future REAL motion controller completion
    input  wire       print_error,
    output wire [2:0] state,
    output wire       capture_req,
    output wire       start_print,
    output wire       job_clear,
    output wire       prompt_valid,
    output wire [2:0] prompt_id,
    output wire       error_latched,
    output wire       unsupported,
    output wire [7:0] unsupported_ascii,
    output wire       x_step,
    output wire       x_dir,
    output wire       y_step,
    output wire       y_dir,
    output wire       punch_enable,
    output wire       motion_enable
);
    wire english_ready;
    wire english_busy;
    reg complete_pending;
    reg saw_nonblank;
    wire empty_job_error;
    wire job_abort = estop || text_error || print_error || unsupported || empty_job_error ||
                     (keyword_valid && (keyword_id == 4 || keyword_id == 5));
    wire clear_converter = job_clear || job_abort || error_latched;
    wire accepting_text = (state == 3'd2) && !complete_pending && !job_abort;
    wire drained_complete = (complete_pending || text_complete) &&
                            !english_busy && !text_valid;
    assign empty_job_error = (state == 3'd2) && drained_complete && !saw_nonblank;
    assign text_ready = accepting_text && english_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) complete_pending <= 0;
        else if (clear_converter || state != 3'd2) complete_pending <= 0;
        else if (text_complete) complete_pending <= 1;
    end

    // Reject an empty/whitespace-only job even if an adapter mistakenly marks
    // it complete. Capacity and full-page buffering remain adapter duties.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) saw_nonblank <= 0;
        else if (clear_converter || state != 3'd2) saw_nonblank <= 0;
        else if (text_valid && text_ready && text_ascii != 8'h20 && text_ascii != 8'h0a)
            saw_nonblank <= 1;
    end

    workflow_fsm workflow (
        .clk(clk), .rst_n(rst_n), .keyword_valid(keyword_valid),
        .keyword_id(keyword_id), .keyword_ready(keyword_ready),
        .text_complete(drained_complete && saw_nonblank),
        .text_error(text_error || unsupported || empty_job_error),
        .print_done(print_done), .print_error(print_error), .estop(estop),
        .state(state), .capture_req(capture_req), .start_print(start_print),
        .job_clear(job_clear), .prompt_valid(prompt_valid),
        .prompt_id(prompt_id), .error_latched(error_latched)
    );
    english_braille english (
        .clk(clk), .rst_n(rst_n), .clear(clear_converter),
        .char_valid(text_valid && accepting_text), .char_ready(english_ready),
        .char_ascii(text_ascii), .out_valid(cell_valid), .out_ready(cell_ready),
        .out_cell(cell_bits), .out_newline(cell_newline), .busy(english_busy),
        .unsupported(unsupported), .unsupported_ascii(unsupported_ascii)
    );

    // Safe logical outputs: no real actuation has been implemented. Board
    // adapter MUST map motion_enable=0 to the driver's physical disabled level
    // (e.g. an active-low EN pin needs inversion) and provide hardware interlock.
    assign x_step = 1'b0;
    assign x_dir = 1'b0;
    assign y_step = 1'b0;
    assign y_dir = 1'b0;
    assign punch_enable = 1'b0;
    assign motion_enable = 1'b0;
endmodule
`default_nettype wire
