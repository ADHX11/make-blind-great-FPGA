`timescale 1ns/1ps
`default_nettype none
// PL workflow reference. Keyword IDs are application events, not an ASR model.
module workflow_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       keyword_valid,
    input  wire [2:0] keyword_id,
    output wire       keyword_ready,
    input  wire       text_complete,
    input  wire       text_error,
    input  wire       print_done,
    input  wire       print_error,
    input  wire       estop,
    output reg  [2:0] state,
    output reg        capture_req,
    output reg        start_print,
    output reg        job_clear,
    output reg        prompt_valid,
    output reg  [2:0] prompt_id,
    output wire       error_latched
);
    localparam [2:0] IDLE=0, WAIT_BOOK=1, WAIT_OCR=2, READY=3,
                     PRINTING=4, DONE=5, ERROR=6;
    localparam [2:0] START=1, COMPLETE=2, PRINT=3, CANCEL=4, STOP=5;
    // Prompts: 1=place book; 2=capturing; 3=ready; 4=printing;
    // 5=done; 6=error; 7=cancelled. Audio playback belongs to the PC adapter.
    assign keyword_ready = 1'b1;
    assign error_latched = (state == ERROR);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            capture_req <= 0;
            start_print <= 0;
            job_clear <= 1;
            prompt_valid <= 0;
            prompt_id <= 0;
        end else begin
            capture_req <= 0;
            start_print <= 0;
            job_clear <= 0;
            prompt_valid <= 0;
            // Faults outrank cancellation and ordinary transitions. ERROR can
            // only be cleared by reset; a speech command cannot release it.
            if (state == ERROR) begin
                state <= ERROR;
            end else if (estop || text_error || print_error ||
                         (keyword_valid && keyword_id == STOP)) begin
                state <= ERROR;
                job_clear <= 1;
                prompt_valid <= 1;
                prompt_id <= 6;
            end else if (keyword_valid && keyword_id == CANCEL) begin
                state <= IDLE;
                job_clear <= 1;
                prompt_valid <= 1;
                prompt_id <= 7;
            end else begin
                case (state)
                    IDLE, DONE: if (keyword_valid && keyword_id == START) begin
                        state <= WAIT_BOOK;
                        job_clear <= 1;
                        prompt_valid <= 1;
                        prompt_id <= 1;
                    end
                    WAIT_BOOK: if (keyword_valid && keyword_id == COMPLETE) begin
                        state <= WAIT_OCR;
                        capture_req <= 1;
                        prompt_valid <= 1;
                        prompt_id <= 2;
                    end
                    WAIT_OCR: if (text_complete) begin
                        state <= READY;
                        prompt_valid <= 1;
                        prompt_id <= 3;
                    end
                    READY: if (keyword_valid && keyword_id == PRINT) begin
                        state <= PRINTING;
                        start_print <= 1;
                        prompt_valid <= 1;
                        prompt_id <= 4;
                    end
                    PRINTING: if (print_done) begin
                        state <= DONE;
                        prompt_valid <= 1;
                        prompt_id <= 5;
                    end
                    default: begin
                        state <= ERROR;
                        job_clear <= 1;
                        prompt_valid <= 1;
                        prompt_id <= 6;
                    end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
