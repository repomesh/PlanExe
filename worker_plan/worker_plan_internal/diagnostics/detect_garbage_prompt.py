"""
Detect garbage prompt.

PlanExe makes plans based on an initial prompt.
The quality of the plan is dependent on the quality of the prompt.
Garbage in, garbage out.
This module will determine if the prompt is garbage.

Determine if it's an underspecified prompt. A prompt that is too vague.
If it's highly ambiguous, and the user doesn't know what they want.
Determine if it's an overspecified prompt.
Determine if it's an nonsensical prompt.
Determine if the user wants to do something that cost money, but they don't have the money.

Flow:
Take the initial prompt, and count number of bytes, characters, words, symbols, lines. Format this as a string, lets call it "prompt_stats".
As part of the user prompt, include the "prompt_stats", so the LLM knows the stats of the initial prompt.

Use structured output with the DetectGarbagePrompt class.

See the simple_plan_prompts.jsonl for examples of good prompts. In this file ignore the short prompts, since they yield somewhat crappy plans. It's the long prompts that results in good plans.
The longer prompts usually include physical locations, and budget and time constraints.
I'm not interested in fictional locations, the locations must be in the real world, otherwise the plan will be non-sense.

Example of crap prompts that yield non-sense plans.. these are what I'm actually seeing in production. 
${PROMPT_TEXT}
blah
todo
hello3
lots of blank spaces
\n
I want to be rich
I want to be famous

TODO: Implement this module. Take inspiration from identify_purpose.py, redline_gate.py, physical_locations.py, premise_attack.py, premortem.py.
TODO: Test this module against the 10 of the longest prompts in the simple_plan_prompts.jsonl file (where it should not trigger garbage detection).
TODO: Test this module against the 10 of the crap prompts (where it should trigger garbage detection).
"""
import time
from math import ceil
import logging
import json
from enum import Enum
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)

class DetectGarbagePrompt(BaseModel):
    """
    Detect garbage prompt.
    """
    includes_physical_locations: Literal["none", "ambiguous", "good"] = Field(
        description="Does the prompt include physical locations? If yes, is it ambiguous? If yes, is it good? If no, is it bad?"
    )
