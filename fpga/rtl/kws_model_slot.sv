`timescale 1ns/1ps
`default_nettype none
// UNIMPLEMENTED AMS/multi-keyword inference slot.
// No trained model, weights, feature pipeline, or accelerator is included.
// Disabled outputs are intentional; no fabricated keyword predictions.
module kws_model_slot (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        pcm_valid,
    input  wire [15:0] pcm_sample,
    output wire        pcm_ready,
    output wire        keyword_valid,
    output wire [2:0]  keyword_id,
    input  wire        keyword_ready,
    output wire        implemented
);
    assign pcm_ready = 1'b0;
    assign keyword_valid = 1'b0;
    assign keyword_id = 3'd0;
    assign implemented = 1'b0;
endmodule
`default_nettype wire
