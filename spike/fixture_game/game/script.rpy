## Minimal fixture game for the control-flow spike.
## Labels for existing tests, plus call-stack spike labels.

default x = 0
default y = 0
default choice_made = ""
default call_result = ""
default inner_result = ""
default exec_result = ""

label start:
    "This is the start label."
    return

label set_x:
    $ x = 42
    "x has been set."

label set_y:
    $ y = 99
    pause

label menu_test:
    menu:
        "Pick a fruit:"
        "Apple":
            $ choice_made = "apple"
        "Banana":
            $ choice_made = "banana"
    "You chose [choice_made]."

## --- Call-stack spike labels ---

label call_with_says:
    $ call_result = "before"
    "First say in called label."
    "Second say in called label."
    $ call_result = "after"
    return

label call_inner:
    $ inner_result = "inner_done"
    "Say from inner label."
    return

label call_nested:
    "Outer label before nested call."
    call call_inner
    $ call_result = "outer_done"
    return

label call_with_jump:
    "Say before jump."
    jump jump_target

label jump_target:
    $ call_result = "jumped"
    "Landed at jump target."

label call_with_menu:
    "Say before menu."
    menu:
        "Pick during call:"
        "Option A":
            $ choice_made = "option_a"
        "Option B":
            $ choice_made = "option_b"
    $ call_result = "menu_done"
    return

label call_no_yields:
    $ call_result = "no_yield_done"
    return

label exec_call_target:
    $ exec_result = "exec_call_done"
    "Say from exec-called label."
    return

init python:
    def trigger_call():
        renpy.call("exec_call_target")
