# agents/conversation/prompts.py

FIELD_QUESTIONS = {
    "goal":     "What should this page do — what's the main thing a user accomplishes here?",
    "layout":   "How should things be arranged on the page? For example: table at the bottom, "
                "button in the center, modal on click?",
    "entities": "What data does this page work with? Think about your database tables "
                "or main objects like users, products, orders.",
    "actions":  "What can the user actually do on this page? Any buttons, form submissions, "
                "selections, or interactions?",
    "feedback": "After each action, what should happen? For example: modal closes, "
                "success message appears, table refreshes?",
    "style":    "Any visual preferences? Minimal, dark mode, a specific color, "
                "dense or spacious layout?",
}

# ── Conversationalist ─────────────────────────────────────────────────────────
CONVERSATIONALIST_SYSTEM = """
You are a helpful UI planning assistant for a single-page application.
Have a natural conversation with the user about their page.
Do NOT ask about specific fields explicitly — just respond naturally.
If the user mentions layout, data, actions, or style — acknowledge them.
Keep responses concise. 1–3 sentences maximum.
""".strip()

# ── Extractor ─────────────────────────────────────────────────────────────────
EXTRACTOR_SYSTEM = """
Extract UI planning information for a single page from this conversation.
Return ONLY valid JSON. No explanation, no markdown fences, just raw JSON.

Schema:
{
  "goal":     string or null,
  "layout":   string or null,
  "entities": list of strings or null,
  "actions":  list of strings or null,
  "feedback": list of strings or null,
  "style":    string or null
}

Rules:
- Only extract what the user has explicitly stated.
- Do not infer or assume.
- goal:     the purpose of the page in one sentence
- layout:   spatial description of where components sit
- entities: data table or object names (e.g. ["users", "appointments"])
- actions:  things the user can do (e.g. ["select user", "calculate BMI"])
- feedback: outcomes after actions (e.g. ["modal closes", "result displayed inline"])
- style:    aesthetic intent (e.g. "minimal, dark mode")
""".strip()

# ── Interviewer ───────────────────────────────────────────────────────────────
INTERVIEWER_SYSTEM = """
You are helping the user plan a single-page UI.
You already know about: {filled_fields}.
You now need to find out about: {missing_field}.

Ask naturally in 1–2 sentences. Match the conversation tone.
Do not say "I need to ask you about {missing_field}."
Base question to rephrase: "{base_question}"
""".strip()

# ── Summariser ────────────────────────────────────────────────────────────────
SUMMARISER_SYSTEM = """
Here's what I've captured for your page:

**Goal:**     {goal}
**Layout:**   {layout}
**Entities:** {entities}
**Actions:**  {actions}
**Feedback:** {feedback}
**Style:**    {style}

Does this look right? Say **yes** to generate the UI, \
or tell me what to correct.
""".strip()