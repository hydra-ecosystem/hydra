// Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

// Regenerate lexer by running 'python setup.py antlr' at project root.
// If you make changes here be sure to update the documentation
// (and update the grammar in website/docs/advanced/override_grammar/*.md)
lexer grammar OverrideLexer;


// Re-usable fragments.
fragment CHAR: [a-zA-Z];
fragment DIGIT: [0-9];
fragment INT_UNSIGNED: '0' | [1-9] (('_')? DIGIT)*;
fragment ESC_BACKSLASH: '\\\\';  // escaped backslash

////////////////////////
// DEFAULT_MODE (KEY) //
////////////////////////

EQUAL: '=' WS? -> mode(VALUE_MODE);

TILDE: '~';
PLUS: '+';
AT: '@';
COLON: ':';
SLASH: '/';

fragment KEY_ESCAPE: '\\' ('.' | '[' | ']' | '=');
fragment KEY_CHAR: CHAR | DIGIT | '_' | '-' | '$';
fragment KEY_ESCAPED: KEY_CHAR* KEY_ESCAPE (KEY_CHAR | KEY_ESCAPE)*;
fragment KEY_SEGMENT: KEY_SPECIAL | INT_UNSIGNED | KEY_ESCAPED;
fragment KEY_BRACKET: '[' (KEY_CHAR | KEY_ESCAPE)+ ']';
VALUE_PATH:
    (
        (KEY_SPECIAL | DOT_PATH) KEY_BRACKET
      | (KEY_SPECIAL | INT_UNSIGNED | DOT_PATH) '.' KEY_ESCAPED
      | KEY_ESCAPED
    ) (KEY_BRACKET | '.' KEY_SEGMENT)*;

KEY_ID: ID -> type(ID);
KEY_SPECIAL: (CHAR|'_'|'$') (CHAR|DIGIT|'_'|'-'|'$')*;  // same as ID but allowing $
DOT_PATH: (KEY_SPECIAL | INT_UNSIGNED) ('.' (KEY_SPECIAL | INT_UNSIGNED))+;

////////////////
// VALUE_MODE //
////////////////

mode VALUE_MODE;

POPEN: WS? '(' WS?;  // whitespaces before to allow `func (x)`
COMMA: WS? ',' WS?;
PCLOSE: WS? ')';
BRACKET_OPEN: '[' WS?;
BRACKET_CLOSE: WS? ']';
BRACE_OPEN: '{' WS?;
BRACE_CLOSE: WS? '}';
VALUE_COLON: WS? ':' WS? -> type(COLON);
VALUE_EQUAL: WS? '=' WS? -> type(EQUAL);

// Numbers.

fragment POINT_FLOAT: INT_UNSIGNED '.' | INT_UNSIGNED? '.' DIGIT (('_')? DIGIT)*;
fragment EXPONENT_FLOAT: (INT_UNSIGNED | POINT_FLOAT) [eE] [+-]? DIGIT (('_')? DIGIT)*;
FLOAT: [+-]? (POINT_FLOAT | EXPONENT_FLOAT | [Ii][Nn][Ff] | [Nn][Aa][Nn]);
INT: [+-]? INT_UNSIGNED;

// Other reserved keywords.

BOOL:
      [Tt][Rr][Uu][Ee]      // TRUE
    | [Ff][Aa][Ll][Ss][Ee]; // FALSE

NULL: [Nn][Uu][Ll][Ll];

UNQUOTED_CHAR: [/\-\\+.$%*@?|];  // other characters allowed in unquoted strings
ID: (CHAR|'_') (CHAR|DIGIT|'_'|'-')*;
// Note: when adding more characters to the ESC rule below, also add them to
// the `_ESC` string in `_internal/grammar/utils.py`.
ESC: (ESC_BACKSLASH | '\\(' | '\\)' | '\\[' | '\\]' | '\\{' | '\\}' |
      '\\:' | '\\=' | '\\,' | '\\ ' | '\\\t')+;
WS: [ \t]+;

// Quoted values for both types of quotes.
// A quoted value is made of the enclosing quotes, and either:
//   - nothing else
//   - an even number of backslashes (meaning they are escaped)
//   - an optional sequence of any character, followed by any non-backslash character,
//     and optionally an even number of backslashes (i.e., also escaped)
// Examples (right hand side: expected content of the resulting string, after un-escaping):
//    ""                      -> <empty>
//    '\\'                    -> \
//    "\\\\"                  -> \\
//    'abc\\'                 -> abc\
//    "abc\\\"def\\\'ghi\\\\" -> abc\"def\\\'ghi\\
QUOTED_VALUE:
      '"' (('\\\\')* | (.)*? ~[\\] ('\\\\')*) '"'     // double quotes
    | '\'' (('\\\\')* | (.)*? ~[\\] ('\\\\')*) '\'';  // single quotes

INTERPOLATION: '${' ~('}')+ '}';
