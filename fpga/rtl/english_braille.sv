`timescale 1ns/1ps
`default_nettype none
// Limited uncontracted English reference, NOT a complete UEB implementation.
// Accepted bytes: ASCII letters, digits, space and LF. No UTF-8 decoding.
// Cell bit 0=dot 1 ... bit 5=dot 6. LF is a separate layout event, not a cell.
// One input character is buffered, producing up to three output events.
module english_braille (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       clear,
    input  wire       char_valid,
    output wire       char_ready,
    input  wire [7:0] char_ascii,
    output wire       out_valid,
    input  wire       out_ready,
    output wire [5:0] out_cell,
    output wire       out_newline,
    output wire       busy,
    output reg        unsupported,
    output reg  [7:0] unsupported_ascii
);
    reg [5:0] queued_cell [0:2];
    reg [2:0] queued_newline;
    reg [1:0] count;
    reg [1:0] index;
    reg numeric_mode;
    wire is_upper = char_ascii >= 8'h41 && char_ascii <= 8'h5a;
    wire is_lower = char_ascii >= 8'h61 && char_ascii <= 8'h7a;
    wire is_digit = char_ascii >= 8'h30 && char_ascii <= 8'h39;
    wire [7:0] lower_ascii = is_upper ? char_ascii + 8'd32 : char_ascii;
    wire needs_letter_mark = numeric_mode && lower_ascii >= 8'h61 && lower_ascii <= 8'h6a;
    wire [7:0] digit_letter = char_ascii == 8'h30 ? 8'h6a : char_ascii + 8'd48;

    function automatic [5:0] letter_cell(input [7:0] letter);
        begin
            case (letter)
                "a":letter_cell=6'h01; "b":letter_cell=6'h03;
                "c":letter_cell=6'h09; "d":letter_cell=6'h19;
                "e":letter_cell=6'h11; "f":letter_cell=6'h0b;
                "g":letter_cell=6'h1b; "h":letter_cell=6'h13;
                "i":letter_cell=6'h0a; "j":letter_cell=6'h1a;
                "k":letter_cell=6'h05; "l":letter_cell=6'h07;
                "m":letter_cell=6'h0d; "n":letter_cell=6'h1d;
                "o":letter_cell=6'h15; "p":letter_cell=6'h0f;
                "q":letter_cell=6'h1f; "r":letter_cell=6'h17;
                "s":letter_cell=6'h0e; "t":letter_cell=6'h1e;
                "u":letter_cell=6'h25; "v":letter_cell=6'h27;
                "w":letter_cell=6'h3a; "x":letter_cell=6'h2d;
                "y":letter_cell=6'h3d; "z":letter_cell=6'h35;
                default:letter_cell=6'h00;
            endcase
        end
    endfunction

    assign char_ready = (count == 0) && !clear;
    assign out_valid = (count != 0) && !clear;
    assign out_cell = queued_cell[index];
    assign out_newline = queued_newline[index];
    assign busy = (count != 0);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            queued_cell[0] <= 0; queued_cell[1] <= 0; queued_cell[2] <= 0;
            queued_newline <= 0;
            count <= 0; index <= 0; numeric_mode <= 0;
            unsupported <= 0; unsupported_ascii <= 0;
        end else if (clear) begin
            count <= 0; index <= 0; numeric_mode <= 0;
            unsupported <= 0; unsupported_ascii <= 0;
            queued_newline <= 0;
        end else begin
            unsupported <= 0;
            if (out_valid && out_ready) begin
                count <= count - 1'b1;
                if (count == 1) index <= 0;
                else index <= index + 1'b1;
            end
            if (char_valid && char_ready) begin
                index <= 0;
                queued_newline <= 0;
                if (is_upper || is_lower) begin
                    numeric_mode <= 0;
                    if (needs_letter_mark && is_upper) begin
                        queued_cell[0] <= 6'h30; // dots 5,6
                        queued_cell[1] <= 6'h20; // capital: dot 6
                        queued_cell[2] <= letter_cell(lower_ascii);
                        count <= 3;
                    end else if (needs_letter_mark || is_upper) begin
                        queued_cell[0] <= needs_letter_mark ? 6'h30 : 6'h20;
                        queued_cell[1] <= letter_cell(lower_ascii);
                        count <= 2;
                    end else begin
                        queued_cell[0] <= letter_cell(lower_ascii);
                        count <= 1;
                    end
                end else if (is_digit) begin
                    numeric_mode <= 1;
                    if (!numeric_mode) begin
                        queued_cell[0] <= 6'h3c; // numeric: dots 3,4,5,6
                        queued_cell[1] <= letter_cell(digit_letter);
                        count <= 2;
                    end else begin
                        queued_cell[0] <= letter_cell(digit_letter);
                        count <= 1;
                    end
                end else if (char_ascii == 8'h20 || char_ascii == 8'h0a) begin
                    numeric_mode <= 0;
                    queued_cell[0] <= 0;
                    queued_newline[0] <= (char_ascii == 8'h0a);
                    count <= 1;
                end else begin
                    numeric_mode <= 0;
                    unsupported <= 1;
                    unsupported_ascii <= char_ascii;
                end
            end
        end
    end
endmodule
`default_nettype wire
