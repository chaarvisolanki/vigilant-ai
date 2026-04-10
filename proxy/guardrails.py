"""
Vigilant-AI Guardrail Engine — Fully Offline Version
=====================================================
No ML model downloads required. All detection is rule-based and instant.
This is actually BETTER for a hackathon demo — zero startup time,
deterministic results, and the judges can read/understand every detection rule.

Detection layers:
  1. Prompt Injection — multi-pattern matching
  2. Jailbreaking — keyword + structure analysis
  3. PII / Secrets — comprehensive regex patterns
  4. Toxicity — keyword scoring
  5. Hallucination — claim density analysis
"""

from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────────────
# PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

# Prompt injection patterns
INJECTION_PATTERNS: list[tuple[str, float]] = [
    # Direct override attempts
    (r"(?i)ignore\s+(all\s+)?(previous\s+)?(your\s+)?instructions", 0.95),
    (r"(?i)disregard\s+(your\s+|all\s+)?(instructions|rules|guidelines|safety)", 0.95),
    (r"(?i)forget\s+(everything|your|all\s+previous)", 0.90),
    (r"(?i)new\s+(system|initial|set\s+of)\s+instructions", 0.90),
    (r"(?i)override\s+(your|system|the)\s+(instructions|prompt|guidelines)", 0.95),
    (r"(?i)you\s+are\s+now\s+(a?\s*|different\s+|new\s+)", 0.70),
    (r"(?i)pretend\s+you\s+(can|have|are)", 0.70),
    (r"(?i)you\s+no\s+longer\s+", 0.80),
    (r"(?i)system\s*prompt\s*(leak|reveal|show|print|tell)", 0.98),
    (r"(?i)(reveal|show|tell|print)\s+(your|the|me)\s+(system\s+)?prompt", 0.98),
    # DAN / jailbreak
    (r"(?i)\bDAN\b", 0.85),
    (r"(?i)\bDAN\b.*mode", 0.90),
    (r"(?i)do\s+anything\s+now", 0.90),
    (r"(?i)#\s*jailbreak", 0.95),
    (r"(?i)gpt4chan", 0.90),
    (r"(?i)developer\s*mode", 0.90),
    (r"(?i)mode:\s*dev", 0.85),
    (r"(?i)dev\s*mode", 0.85),
    (r"(?i)unlocked\s*mode", 0.80),
    (r"(?i)unrestricted\s*mode", 0.85),
    (r"(?i)numbers.*only.*mode", 0.75),
    # Leetspeak / encoding tricks
    (r"\\x[0-9a-f]{2}", 0.70),
    (r"&#[0-9]{3}", 0.60),
    (r"(?i)base64\s*(decode|decode\s+this)", 0.70),
    # Roleplay overrides
    (r"(?i)you\s+are\s+a\s+(role|character|persona)", 0.60),
    (r"(?i)now\s+roleplay\s+as", 0.65),
    (r"(?i)play\s+(the\s+)?(role\s+of|character)", 0.60),
    # Hidden instructions
    (r"(?i)<\|im_start\|>", 0.75),  # OAI chat template injection
    (r"(?i)<\|im_end\|>", 0.75),
    (r"(?i)\\n\\n\\n", 0.50),       # Excessive newlines to confuse
    (r"(?i)user:\s*$", 0.50),       # Trailing "user:" to confuse
    # Context stuffing
    (r"(?i){.*role.*system.*}", 0.60),
    (r"(?i)\[INST\].*\[/INST\]", 0.70),  # Llama instruction injection
    (r"(?i)<<SYS>>", 0.70),
    # Confidential data exfil
    (r"(?i)(your\s+)?(system\s+)?prompt\s+(is|:)\s*['\"]", 0.90),
    (r"(?i)begin\s+(your\s+)?system\s+prompt", 0.90),
]

# Jailbreak-specific keywords (trigger even without patterns above)
JAILBREAK_KEYWORDS = [
    "dan", "do anything now", "developer mode", "dev mode",
    "jailbreak", "jail broken", "ignore previous",
    "new instructions", "override", "unrestricted",
    "unlocked", "nurse model", "STFU", "角色扮演",
]

# PII / Secrets patterns
PII_PATTERNS: list[tuple[str, str]] = [
    ("API_KEY",     r"(?i)(api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|bearer\s+token)\s*(?:is|:|\=)\s*['\"]?[\w\-]{10,}['\"]?"),
    ("GROQ_KEY",    r"(?i)gsk_[a-zA-Z0-9]{20,}"),
    ("OPENAI_KEY",  r"(?i)sk-[a-zA-Z0-9\-]{10,}"),
    ("GENERIC_SECRET", r"(?i)(?:secret|pwd|passwd|token|auth|private)\s*(?:is|:|\=)\s*['\"]?[\w\-]{8,}['\"]?"),

    ("EMAIL",       r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),
    ("PHONE_IN",    r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"),
    ("PHONE_US",    r"\b\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"),
    ("PAN",         r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    ("CREDIT_CARD", r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
    ("PASSWORD",    r"(?i)(?:my\s+)?password\s*(?:is|:|\=)\s*['\"]?[^\s'\"]{4,}"),
    ("IP_ADDRESS",  r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ("URL_SENSITIVE", r"(?i)https?://[^\s]*\b(key|token|secret|password|auth)[^\s]*"),
    ("SSN",         r"\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b"),
]

# Toxicity — weighted keyword categories
TOXIC_CATEGORIES = {
    "hate_speech": [
        ("kill", 0.7), ("murder", 0.8), ("terror", 0.9), ("bomb", 0.9),
        ("explosive", 0.8), ("attack", 0.5), ("harm", 0.4), ("abuse", 0.5),
        ("racist", 0.9), ("sexist", 0.8), ("discriminat", 0.7), ("slur", 0.9),
        ("bigot", 0.9), ("genocide", 1.0), ("lynch", 0.9), ("rape", 0.9),
    ],
    "violence": [
        ("weapon", 0.6), ("gun", 0.6), ("knife", 0.5), ("blade", 0.5),
        ("assault", 0.7), ("torture", 0.8), ("maim", 0.8), ("brutal", 0.6),
        ("gore", 0.7), ("blood", 0.4),
    ],
    "dangerous_advice": [
        ("how to make bomb", 1.0), ("how to build weapon", 0.9),
        ("how to poison", 0.9), ("synthesize drug", 0.9),
        ("how to hack", 0.7), ("exploit vulnera", 0.7), ("sql inject", 0.6),
    ],
    "self_harm": [
        ("suicide", 0.9), ("self harm", 0.9), ("kill myself", 0.9), ("end my life", 0.9),
    ],
    "harassment": [
        ("stupid", 0.2), ("idiot", 0.3), ("dumb", 0.2), ("worthless", 0.5),
        ("should die", 0.8), ("go die", 0.9),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuardrailResult:
    passed: bool
    risk_score: float           # 0.0 → 1.0
    risk_type: Optional[str]     # injection | pii | toxicity | hallucination
    reason: str
    redacted_text: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PromptAnalysis:
    injection_score: float
    pii_entities: dict
    has_jailbreak: bool
    raw_text: str
    redacted_text: str
    risk_score: float


# ─────────────────────────────────────────────────────────────────────────────
# GUARDRAIL ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class GuardrailEngine:
    """
    Multi-layer, fully-offline guardrail engine.
    No ML models required — all detection is rule-based.
    Deterministic, instant, and auditable.
    """

    def __init__(self, device: Optional[str] = None):
        self.device = device or "cpu"
        self._initialized = True
        # Pre-compile regex for performance
        self._injection_re = [(re.compile(p, re.IGNORECASE), s) for p, s in INJECTION_PATTERNS]
        self._pii_re = [(k, re.compile(p, re.IGNORECASE)) for k, p in PII_PATTERNS]

    def initialize(self):
        """No-op for API compatibility — all models are rule-based."""
        self._initialized = True

    # ── Injection / Jailbreak Detection ────────────────────────────────────

    def detect_injection(self, text: str) -> tuple[float, bool]:
        """
        Returns (injection_score, is_jailbreak).
        Checks against 30+ pre-compiled regex patterns + jailbreak keywords.
        """
        score = 0.0
        jailbreak = False

        # Pattern matching
        for pattern, weight in self._injection_re:
            if pattern.search(text):
                score = max(score, weight)
                if weight >= 0.85:
                    jailbreak = True

        # Keyword check (only escalates if score already elevated)
        text_lower = text.lower()
        for kw in JAILBREAK_KEYWORDS:
            if kw.lower() in text_lower:
                if score > 0:
                    jailbreak = True
                    score = max(score, 0.70)
                else:
                    # Single keyword = mild signal, not decisive alone
                    score = max(score, 0.40)

        # Structural signals — very long prompts with many special chars
        special_char_density = sum(1 for c in text if c in "<>{}\\|`") / max(len(text), 1)
        if special_char_density > 0.02:
            score = max(score, 0.50)

        # Repeated instruction keywords
        words = text_lower.split()
        instruction_words = ["ignore", "disregard", "forget", "override", "new", "pretend", "roleplay"]
        instruction_count = sum(1 for w in words if w in instruction_words)
        if instruction_count >= 3:
            score = max(score, min(0.95, 0.5 + instruction_count * 0.15))

        return min(1.0, score), jailbreak

    # ── PII Detection & Redaction ──────────────────────────────────────────

    def detect_and_redact_pii(self, text: str) -> tuple[dict, str]:
        """Find PII/secrets and replace with [TYPE] placeholders."""
        entities = {}
        redacted = text

        for label, pattern in self._pii_re:
            matches = list(pattern.finditer(redacted))
            if matches:
                entities.setdefault(label, [])
                for m in reversed(matches):  # reverse to preserve offsets
                    entities[label].append(m.group())
                    redacted = redacted[:m.start()] + f"[REDACTED_{label}]" + redacted[m.end():]

        return entities, redacted

    # ── Toxicity Detection ─────────────────────────────────────────────────

    def detect_toxicity(self, text: str) -> float:
        """Rule-based toxicity scoring across multiple harm categories."""
        if not text.strip():
            return 0.0

        text_lower = text.lower()
        words = set(text_lower.split())
        score = 0.0

        for category, keywords in TOXIC_CATEGORIES.items():
            for kw, weight in keywords:
                if kw.lower() in text_lower:
                    score = max(score, weight)

        # Density check — single keyword in a long text is less concerning
        if len(text) > 200:
            score *= min(1.0, 100 / len(text) * 2)

        # Check for "all-caps rage" pattern
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        if caps_ratio > 0.4 and len(text) > 20:
            score = max(score, 0.50)

        return min(1.0, score)

    # ── Hallucination Scoring ──────────────────────────────────────────────

    def score_hallucination(self, prompt: str, response: str) -> float:
        """
        Detect likely hallucinations by measuring claim density vs context.
        High score = response makes many specific claims the prompt didn't discuss.
        """
        if not response.strip():
            return 0.0

        # Extract claims: numbers, specific dates, percentages, product names
        numbers_in_response = re.findall(r"\b\d+(?:\.\d+)?%?\b", response)
        proper_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", response)
        years = re.findall(r"\b(19|20)\d{2}\b", response)

        response_words = response.lower().split()
        prompt_words = set(prompt.lower().split())

        # Suspicious phrases (often indicate hallucination)
        halluc_indicators = [
            r"according to (the )?(recent |latest )?(report|study|research|article)",
            r"(it is|studies show|researchers have) (proven|shown|demonstrated|found)",
            r"as (stated|mentioned|noted) in (the )?(above|previous|earlier)",
            r"the (above |following )?document (states|says|mentions|shows)",
            r"(note|please note|important):",
            r"\*+\s*[A-Za-z]",  # markdown bold abuse for fake citations
            r"source:", r"citation:", r"reference:",
            r"^https?://",  # URLs without prior context
        ]
        indicator_matches = 0
        for p in halluc_indicators:
            if re.search(p, response, re.IGNORECASE):
                indicator_matches += 1

        # Claim density: many numbers/names in a response to a short simple prompt
        prompt_len = len(prompt.split())
        claim_count = len(numbers_in_response) + len(proper_nouns) + len(years)
        claim_density = claim_count / max(len(response_words), 1)

        # Short prompt + lots of specific claims = suspicious
        base_score = 0.0
        if claim_density > 0.15:
            base_score += 0.4
        if len(numbers_in_response) > 5:
            base_score += 0.3
        if indicator_matches >= 2:
            base_score += 0.4
        elif indicator_matches == 1:
            base_score += 0.2

        # Boost if response has specific claims but prompt had none
        prompt_claims = len(re.findall(r"\b\d+\b", prompt))
        if claim_count > 3 and prompt_claims < 2:
            base_score += 0.3

        return min(1.0, base_score)

    # ── Full Pipeline ──────────────────────────────────────────────────────

    def analyze_prompt(self, text: str) -> PromptAnalysis:
        """Run all input checks on a prompt."""
        injection_score, is_jailbreak = self.detect_injection(text)
        pii_entities, redacted = self.detect_and_redact_pii(text)
        risk = max(injection_score, len(pii_entities) * 0.25)
        if is_jailbreak:
            risk = max(risk, 0.80)
        return PromptAnalysis(
            injection_score=injection_score,
            pii_entities=pii_entities,
            has_jailbreak=is_jailbreak,
            raw_text=text,
            redacted_text=redacted,
            risk_score=risk,
        )

    def check_guardrails(
        self, prompt: str, response: str,
        injection_threshold: float = 0.60,
        toxicity_threshold: float = 0.65,
        hallucination_threshold: float = 0.75,
    ) -> GuardrailResult:
        """Run full guardrail pipeline. Returns GuardrailResult."""
        # Layer 1: Input — injection check
        analysis = self.analyze_prompt(prompt)
        if analysis.injection_score >= injection_threshold:
            return GuardrailResult(
                passed=False, risk_score=analysis.injection_score,
                risk_type="injection",
                reason=f"Prompt injection detected (score={analysis.injection_score:.2f})",
                redacted_text=analysis.redacted_text,
            )

        # Layer 2: Input — PII
        if analysis.pii_entities:
            return GuardrailResult(
                passed=False, risk_score=0.75,
                risk_type="pii",
                reason=f"PII detected: {', '.join(analysis.pii_entities.keys())}",
                redacted_text=analysis.redacted_text,
            )

        # Layer 2b: Input — toxic intent (prompt asking model to generate harmful content)
        prompt_tox = self.detect_toxicity(prompt)
        if prompt_tox >= toxicity_threshold * 0.8:
            return GuardrailResult(
                passed=False, risk_score=prompt_tox,
                risk_type="toxicity",
                reason=f"Toxic intent in prompt (score={prompt_tox:.2f})",
            )

        # Layer 3: Output — toxicity (only meaningful with real LLM response)
        tox_score = self.detect_toxicity(response)
        if tox_score >= toxicity_threshold:
            return GuardrailResult(
                passed=False, risk_score=tox_score,
                risk_type="toxicity",
                reason=f"Toxic output detected (score={tox_score:.2f})",
            )

        # Layer 4: Output — hallucination
        hall_score = self.score_hallucination(prompt, response)
        if hall_score >= hallucination_threshold:
            return GuardrailResult(
                passed=False, risk_score=hall_score,
                risk_type="hallucination",
                reason=f"High hallucination score ({hall_score:.2f}) — response makes unsourced claims",
            )

        return GuardrailResult(
            passed=True, risk_score=0.0,
            risk_type=None, reason="All guardrails passed",
        )
