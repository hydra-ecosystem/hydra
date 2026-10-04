// Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

// Regenerate parser by running 'python setup.py antlr' at project root.
// If you make changes here be sure to update the documentation
// (and update the grammar in website/docs/advanced/override_grammar/*.md)
parser grammar OverrideParser;
options {tokenVocab = OverrideLexer;}

// High-level command-line override.

override: (
      key EQUAL value?                           // key=value, key= (for empty value)
    | TILDE key (EQUAL value?)?                  // ~key | ~key=value
    | PLUS PLUS? key EQUAL value?                // +key= | +key=value | ++key=value
) EOF;

// Key:
key : packageOrGroup (AT package)? | VALUE_PATH; // key | group@pkg | items[0]

packageOrGroup: package | ID (SLASH ID)+;        // db, hydra/launcher
package: ( | ID | KEY_SPECIAL | DOT_PATH);       // db, $db, hydra.launcher, or the empty (for _global_ package)

// Elements (that may be swept over).

value: element | simpleChoiceSweep;

element:
      primitive
    | listContainer
    | dictContainer
    | function
;

simpleChoiceSweep:
      element (COMMA element)+                   // value1,value2,value3
;

// Functions.

argName: ID EQUAL;
function: ID POPEN (argName? element (COMMA argName? element )* )? PCLOSE;

// Data structures.

listContainer: BRACKET_OPEN                      // [], [1,2,3], [a,b,[1,2]]
    (element(COMMA element)*)?
BRACKET_CLOSE;

dictContainer: BRACE_OPEN (dictKeyValuePair (COMMA dictKeyValuePair)*)? BRACE_CLOSE;  // {}, {a:10,b:20}
dictKeyValuePair: dictKey COLON element;

// Primitive types.

primitive:
      QUOTED_VALUE                               // 'hello world', "hello world"
    | (   ID                                     // foo-bar_10
        | NULL                                   // null, NULL
        | INT                                    // 0, 10, -20, 1_000_000
        | FLOAT                                  // 3.14, -20.0, 1e-1, -10e3
        | BOOL                                   // true, TrUe, false, False
        | INTERPOLATION                          // ${foo.bar}, ${oc.env:USER,me}
        | UNQUOTED_CHAR                          // /, -, \, +, ., $, %, *, @, ?, |
        | COLON                                  // :
        | ESC                                    // \\, \(, \), \[, \], \{, \}, \:, \=, \ , \\t, \,
        | WS                                     // whitespaces
    )+;

// Same as `primitive` except that `COLON` and `INTERPOLATION` are not allowed.
dictKey:
    (   ID                                     // foo-bar_10
      | NULL                                   // null, NULL
      | INT                                    // 0, 10, -20, 1_000_000
      | FLOAT                                  // 3.14, -20.0, 1e-1, -10e3
      | BOOL                                   // true, TrUe, false, False
      | UNQUOTED_CHAR                          // /, -, \, +, ., $, %, *, @, ?, |
      | ESC                                    // \\, \(, \), \[, \], \{, \}, \:, \=, \ , \\t, \,
      | WS                                     // whitespaces
    )+;
