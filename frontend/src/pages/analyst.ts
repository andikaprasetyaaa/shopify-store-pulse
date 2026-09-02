import { askAnalyst, fetchAnalystStatus } from "../api";
import { content, state } from "../state";
import type {
    AnalystResponse,
    AnalystTurn,
    ChatMessage,
} from "../types";

/**
 * The analyst page: a conversation, not a form.
 *
 * The transcript lives in `state.analystChat` and is
 * posted back with every question, because the API is
 * stateless - the server keeps no session, so the
 * client is what remembers. Only completed turns are
 * sent: a pending placeholder or a failed turn would
 * teach the model that an error was part of the
 * conversation.
 *
 * Two rules shape the rendering below.
 *
 * First, the model's answer is untrusted text. It is
 * rendered entirely with createElement and textContent -
 * never innerHTML - so nothing the model emits can become
 * markup. That is also why the inline formatter below builds
 * <strong> elements itself instead of substituting tags into
 * a string.
 *
 * Second, the answer's structure is a request, not a
 * guarantee. The six headings are detected if present and the
 * text degrades to plain paragraphs if the model words them
 * differently, because a layout that breaks when the model
 * improvises is worse than no layout.
 */

const SECTIONS = [
    "Summary",
    "Evidence",
    "Likely explanation",
    "Forecast",
    "Priority",
    "Recommended investigation",
] as const;

/** The prompt's three evidence labels. */
const LABELS = [
    "OBSERVED",
    "FORECAST",
    "INFERENCE",
] as const;

const PRESETS: ReadonlyArray<[string, string]> = [
    [
        "Explain current state",
        "Explain the store's current state using the supplied data.",
    ],
    [
        "Biggest risk",
        "What is the single biggest risk visible in this data, and how confident can we be about it?",
    ],
    [
        "Read the forecast",
        "Explain the forecast and how much trust the backtest justifies.",
    ],
    [
        "Inventory exposure",
        "What does the inventory data say about stock risk?",
    ],
];

/**
 * Strips one line down to a bare heading name so
 * "**3. Likely explanation**", "### Likely explanation" and
 * "3. Likely explanation" all match.
 */
function headingOf(line: string): string | null {
    const bare = line
        .trim()
        .replace(/^#{1,6}\s*/, "")
        .replace(/^\*\*(.*)\*\*$/, "$1")
        .replace(/^\d+\s*[.)]\s*/, "")
        .replace(/[:.]\s*$/, "")
        .trim();

    const match = SECTIONS.find(
        (name) =>
            name.toLowerCase() === bare.toLowerCase(),
    );

    return match ?? null;
}

const LABEL_PATTERN = new RegExp(
    `\\b(${LABELS.join("|")})\\b`,
    "g",
);

/**
 * Marks every OBSERVED / FORECAST / INFERENCE token in a
 * run of plain text.
 *
 * The model does not reliably put the label at the front of
 * a line: real answers say "OBSERVED period revenue is ...",
 * "The FORECAST model provides ..." and "is OBSERVED at
 * $602,570" in the same reply. Matching only a leading
 * "LABEL:" therefore highlighted nothing at all. Marking the
 * word wherever it appears is what actually keeps the three
 * kinds of claim apart on screen - which is the entire point
 * of the prompt asking for them.
 */
function markLabels(
    parent: HTMLElement,
    text: string,
): void {
    let cursor = 0;

    LABEL_PATTERN.lastIndex = 0;

    for (
        let match = LABEL_PATTERN.exec(text);
        match !== null;
        match = LABEL_PATTERN.exec(text)
    ) {
        if (match.index > cursor) {
            parent.append(
                document.createTextNode(
                    text.slice(cursor, match.index),
                ),
            );
        }

        const mark =
            document.createElement("span");

        mark.className =
            `evidence-label ${match[0]}`;

        mark.textContent = match[0];

        parent.append(mark);

        cursor = match.index + match[0].length;
    }

    if (cursor < text.length) {
        parent.append(
            document.createTextNode(
                text.slice(cursor),
            ),
        );
    }
}

/**
 * Renders one line of body text into `parent`, handling
 * **bold** and the evidence labels.
 */
function inline(
    parent: HTMLElement,
    text: string,
): void {
    // A label directly followed by a colon is the model
    // introducing a claim; drop the colon so the chip does
    // not read as "OBSERVED :".
    const rest = text.replace(
        new RegExp(
            `^\\s*\\*{0,2}(${LABELS.join("|")})\\*{0,2}\\s*:\\s*`,
        ),
        "$1 ",
    );

    for (const [index, piece] of rest
        .split("**")
        .entries()) {
        if (piece === "") {
            continue;
        }

        if (index % 2 === 1) {
            const strong =
                document.createElement("strong");

            markLabels(strong, piece);

            parent.append(strong);

            continue;
        }

        markLabels(parent, piece);
    }
}

function renderBlock(
    parent: HTMLElement,
    lines: string[],
): void {
    let list: HTMLUListElement | null = null;

    for (const line of lines) {
        const trimmed = line.trim();

        if (trimmed === "") {
            list = null;

            continue;
        }

        const bullet = /^[-*•]\s+/.test(trimmed);

        if (bullet) {
            if (list === null) {
                list = document.createElement("ul");

                list.className = "answer-list";

                parent.append(list);
            }

            const item = document.createElement("li");

            inline(
                item,
                trimmed.replace(/^[-*•]\s+/, ""),
            );

            list.append(item);

            continue;
        }

        list = null;

        const paragraph =
            document.createElement("p");

        paragraph.className = "answer-text";

        inline(paragraph, trimmed);

        parent.append(paragraph);
    }
}

function renderAnswer(answer: string): HTMLElement {
    const wrap = document.createElement("div");

    wrap.className = "answer";

    const lines = answer.split("\n");

    let current: HTMLElement | null = null;
    let buffer: string[] = [];

    const flush = (): void => {
        if (buffer.length === 0) {
            return;
        }

        renderBlock(current ?? wrap, buffer);

        buffer = [];
    };

    for (const line of lines) {
        const heading = headingOf(line);

        if (heading === null) {
            buffer.push(line);

            continue;
        }

        flush();

        const section =
            document.createElement("section");

        section.className = "answer-section";

        const title = document.createElement("h3");

        title.className = "answer-heading";
        title.textContent = heading;

        section.append(title);

        wrap.append(section);

        current = section;
    }

    flush();

    return wrap;
}

function notice(
    text: string,
    kind: "notice" | "error" = "notice",
): HTMLElement {
    const node = document.createElement("div");

    node.className = kind;
    node.textContent = text;

    return node;
}

export async function renderAnalyst(): Promise<void> {
    const status = await fetchAnalystStatus();

    content.innerHTML = `

        <div class="chat">

            <div class="chat-bar">

                <div class="chat-bar-text">

                    <div class="chat-bar-title">
                        Store Pulse Analyst
                    </div>

                    <div
                        id="chat-meta"
                        class="chat-bar-meta"
                    ></div>

                </div>

                <button
                    id="chat-reset"
                    type="button"
                    class="chat-reset"
                >
                    New chat
                </button>

            </div>

            <div
                id="chat-log"
                class="chat-log"
                tabindex="0"
                role="log"
                aria-live="polite"
                aria-label="Conversation"
            ></div>

            <div class="chat-composer">

                <div class="composer-box">

                    <textarea
                        id="chat-input"
                        class="composer-input"
                        rows="1"
                        placeholder="Ask about this store's data…"
                        aria-label="Your question"
                    ></textarea>

                    <button
                        id="chat-send"
                        type="button"
                        class="composer-send"
                        aria-label="Send question"
                    >
                        <span aria-hidden="true">↑</span>
                    </button>

                </div>

                <div class="chat-hint">
                    Enter sends · Shift + Enter adds a line ·
                    answers cite only the figures this
                    dashboard already holds
                </div>

            </div>

        </div>
    `;

    const log = requireIn("chat-log");
    const meta = requireIn("chat-meta");
    const reset = requireIn(
        "chat-reset",
    ) as HTMLButtonElement;
    const input = requireIn(
        "chat-input",
    ) as HTMLTextAreaElement;
    const send = requireIn(
        "chat-send",
    ) as HTMLButtonElement;

    if (!status.configured) {
        log.replaceChildren(
            notice(
                status.error ??
                    "The analyst is not configured.",
                "error",
            ),
        );

        input.disabled = true;
        send.disabled = true;
        reset.disabled = true;

        return;
    }

    meta.textContent = describeContext(
        status.model,
    );

    /** Repaints the transcript and pins it to the bottom. */
    const paint = (): void => {
        const empty = state.analystChat.length === 0;

        log.classList.toggle("empty", empty);

        log.replaceChildren(
            ...(empty
                ? [welcome(ask)]
                : state.analystChat.map(turn)),
        );

        log.scrollTop = log.scrollHeight;
    };

    /** The turns the model is allowed to see. */
    const sendableHistory = (): AnalystTurn[] =>
        state.analystChat
            .filter(
                (message) =>
                    message.pending !== true &&
                    message.error !== true,
            )
            .map((message) => ({
                role: message.role,
                text: message.text,
            }));

    async function ask(
        question: string,
    ): Promise<void> {
        const asked = question.trim();

        if (asked === "" || send.disabled) {
            return;
        }

        // Captured before the new turns are pushed, so
        // the model receives the conversation as it
        // stood when the question was asked.
        const history = sendableHistory();

        state.analystChat.push({
            role: "user",
            text: asked,
        });

        state.analystChat.push({
            role: "model",
            text: "",
            pending: true,
        });

        state.analystQuestion = "";

        input.value = "";

        resize(input);

        send.disabled = true;

        paint();

        let result: AnalystResponse;

        try {
            result = await askAnalyst(
                asked,
                state.days,
                state.forecastMetric,
                state.forecastHorizon,
                history,
            );
        } catch (error) {
            settle(
                error instanceof Error
                    ? error.message
                    : String(error),
                true,
            );

            return;
        }

        if (
            result.error !== null ||
            result.answer === null
        ) {
            settle(
                result.error ??
                    "The analyst returned no answer.",
                true,
            );

            return;
        }

        settle(
            result.answer,
            false,
            describeAnswer(result),
        );

        meta.textContent = describeContext(
            result.model ?? status.model,
            result.context_summary?.order_end ?? null,
        );
    }

    /** Replaces the pending placeholder with the outcome. */
    function settle(
        text: string,
        failed: boolean,
        note?: string,
    ): void {
        const pendingIndex =
            state.analystChat.findIndex(
                (message) => message.pending === true,
            );

        const settled: ChatMessage = {
            role: "model",
            text,
            ...(failed ? { error: true } : {}),
            ...(note === undefined
                ? {}
                : { meta: note }),
        };

        if (pendingIndex === -1) {
            state.analystChat.push(settled);
        } else {
            state.analystChat[pendingIndex] = settled;
        }

        send.disabled = false;

        paint();

        input.focus();
    }

    send.addEventListener("click", () => {
        void ask(input.value);
    });

    reset.addEventListener("click", () => {
        state.analystChat.length = 0;

        state.analystQuestion = "";

        input.value = "";

        resize(input);

        paint();

        input.focus();
    });

    input.addEventListener("input", () => {
        state.analystQuestion = input.value;

        resize(input);
    });

    // Enter sends; Shift+Enter keeps a newline, since the
    // box is a textarea for multi-line questions.
    input.addEventListener("keydown", (event) => {
        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();

            void ask(input.value);
        }
    });

    input.value = state.analystQuestion;

    resize(input);

    paint();
}


/**
 * Looks an element up inside the page that was just
 * written, failing loudly rather than rendering a dead
 * control.
 */
function requireIn(id: string): HTMLElement {
    const element =
        content.querySelector<HTMLElement>(`#${id}`);

    if (element === null) {
        throw new Error(
            `Missing element #${id} in the analyst page.`,
        );
    }

    return element;
}


/**
 * Grows the composer with its content up to a ceiling,
 * after which it scrolls. A box that grows without limit
 * eventually pushes the conversation off the screen.
 */
function resize(input: HTMLTextAreaElement): void {
    input.style.height = "auto";

    input.style.height = `${Math.min(
        input.scrollHeight,
        200,
    )}px`;
}


function describeContext(
    model: string | null,
    orderEnd: string | null = null,
): string {
    const parts = [
        model ?? "Gemini",
        `${state.days}-day window`,
    ];

    if (orderEnd !== null) {
        parts.push(`orders through ${orderEnd}`);
    }

    return parts.join(" · ");
}


function describeAnswer(
    result: AnalystResponse,
): string {
    const parts: string[] = [];

    if (result.cached) {
        parts.push("cached");
    }

    if ((result.history_turns ?? 0) > 0) {
        parts.push(
            `with ${result.history_turns} earlier turns`,
        );
    }

    return parts.join(" · ");
}


/** One message in the transcript. */
function turn(message: ChatMessage): HTMLElement {
    const row = document.createElement("div");

    row.className = `turn ${message.role}`;

    if (message.role === "user") {
        const bubble =
            document.createElement("div");

        bubble.className = "bubble";
        bubble.textContent = message.text;

        row.append(bubble);

        return row;
    }

    const role = document.createElement("div");

    role.className = "turn-role";
    role.textContent = "Analyst";

    row.append(role);

    const body = document.createElement("div");

    body.className = "turn-body";

    if (message.pending === true) {
        row.classList.add("pending");

        body.append(thinking());

        row.append(body);

        return row;
    }

    if (message.error === true) {
        row.classList.add("failed");

        body.append(
            notice(message.text, "error"),
        );

        row.append(body);

        return row;
    }

    body.append(renderAnswer(message.text));

    row.append(body);

    if (message.meta !== undefined && message.meta !== "") {
        const note = document.createElement("div");

        note.className = "turn-meta";
        note.textContent = message.meta;

        row.append(note);
    }

    return row;
}


/**
 * The waiting indicator.
 *
 * Three dots rather than a spinner: it occupies the
 * place the answer will appear, so the transcript does
 * not jump when the text arrives.
 */
function thinking(): HTMLElement {
    const wrap = document.createElement("div");

    wrap.className = "thinking";

    wrap.setAttribute("aria-label", "Thinking");

    for (let index = 0; index < 3; index += 1) {
        wrap.append(
            document.createElement("span"),
        );
    }

    return wrap;
}


/**
 * The empty state.
 *
 * It carries the presets, so an empty conversation
 * still offers somewhere to start - and it states the
 * one limit worth knowing before the first question.
 */
function welcome(
    ask: (question: string) => Promise<void>,
): HTMLElement {
    const wrap = document.createElement("div");

    wrap.className = "chat-welcome";

    const title = document.createElement("div");

    title.className = "welcome-title";
    title.textContent =
        "What would you like to know?";

    const sub = document.createElement("p");

    sub.className = "welcome-sub";
    sub.textContent =
        "I explain the figures this dashboard already " +
        "holds - orders, inventory, the funnel and the " +
        "forecast. I never compute new ones, and I " +
        "cannot change anything in Shopify.";

    const row = document.createElement("div");

    row.className = "preset-row";

    for (const [label, question] of PRESETS) {
        const button =
            document.createElement("button");

        button.type = "button";
        button.className = "preset";
        button.textContent = label;

        button.addEventListener("click", () => {
            void ask(question);
        });

        row.append(button);
    }

    wrap.append(title, sub, row);

    return wrap;
}
