import { askAnalyst, fetchAnalystStatus } from "../api";
import { content, state } from "../state";
import type { AnalystResponse } from "../types";

/**
 * The analyst page.
 *
 * Two rules shape this file.
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
        <div id="analyst-status"></div>

        <div class="card analyst-ask">

            <label
                class="metric-label"
                for="analyst-question"
            >
                Ask about this data
            </label>

            <textarea
                id="analyst-question"
                class="control analyst-input"
                rows="3"
                placeholder="e.g. why did orders fall yesterday?"
            ></textarea>

            <div
                id="analyst-presets"
                class="preset-row"
            ></div>

            <div class="analyst-actions">

                <button
                    id="analyst-send"
                    type="button"
                    class="refresh analyst-send"
                >
                    Ask the analyst
                </button>

                <span
                    id="analyst-meta"
                    class="sidebar-small"
                ></span>

            </div>

        </div>

        <div id="analyst-answer"></div>
    `;

    const statusBox =
        content.querySelector<HTMLElement>(
            "#analyst-status",
        );

    const input =
        content.querySelector<HTMLTextAreaElement>(
            "#analyst-question",
        );

    const presets =
        content.querySelector<HTMLElement>(
            "#analyst-presets",
        );

    const send =
        content.querySelector<HTMLButtonElement>(
            "#analyst-send",
        );

    const meta = content.querySelector<HTMLElement>(
        "#analyst-meta",
    );

    const answerBox =
        content.querySelector<HTMLElement>(
            "#analyst-answer",
        );

    if (
        statusBox === null ||
        input === null ||
        presets === null ||
        send === null ||
        meta === null ||
        answerBox === null
    ) {
        return;
    }

    if (!status.configured) {
        statusBox.append(
            notice(
                status.error ??
                    "The analyst is not configured.",
                "error",
            ),
        );

        input.disabled = true;
        send.disabled = true;

        return;
    }

    input.value = state.analystQuestion;

    for (const [label, question] of PRESETS) {
        const button =
            document.createElement("button");

        button.type = "button";
        button.className = "preset";
        button.textContent = label;

        button.addEventListener("click", () => {
            input.value = question;

            state.analystQuestion = question;

            void ask();
        });

        presets.append(button);
    }

    const ask = async (): Promise<void> => {
        const question = input.value.trim();

        state.analystQuestion = question;

        send.disabled = true;
        send.textContent = "Thinking…";

        meta.textContent = "";

        answerBox.replaceChildren(
            notice(
                "Reading the dashboard's numbers and "
                    + "asking " + (status.model ?? "Gemini")
                    + "…",
            ),
        );

        let result: AnalystResponse;

        try {
            result = await askAnalyst(
                question,
                state.days,
                state.forecastMetric,
                state.forecastHorizon,
            );
        } catch (error) {
            answerBox.replaceChildren(
                notice(
                    error instanceof Error
                        ? error.message
                        : String(error),
                    "error",
                ),
            );

            send.disabled = false;
            send.textContent = "Ask the analyst";

            return;
        }

        send.disabled = false;
        send.textContent = "Ask the analyst";

        if (
            result.error !== null ||
            result.answer === null
        ) {
            answerBox.replaceChildren(
                notice(
                    result.error ??
                        "The analyst returned no answer.",
                    "error",
                ),
            );

            return;
        }

        answerBox.replaceChildren(
            renderAnswer(result.answer),
        );

        const summary = result.context_summary;

        meta.textContent =
            `${result.model ?? "model"} · ` +
            `${summary?.reporting_window_days ?? state.days}-day window · ` +
            `orders through ${summary?.order_end ?? "N/A"}` +
            (result.cached ? " · cached" : "");
    };

    send.addEventListener("click", () => {
        void ask();
    });

    // Enter sends; Shift+Enter keeps a newline, since the
    // box is a textarea for multi-line questions.
    input.addEventListener("keydown", (event) => {
        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();

            void ask();
        }
    });
}
