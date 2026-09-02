import "./styles.css";

import { fetchDataHealth } from "./api";
import {
    disposeCharts,
    redrawCharts,
} from "./charts";
import { renderControls } from "./controls";
import { escapeHtml, formatInt } from "./format";
import { renderAnalyst } from "./pages/analyst";
import { renderData } from "./pages/data";
import { renderForecast } from "./pages/forecast";
import { renderFunnel } from "./pages/funnel";
import { renderInventory } from "./pages/inventory";
import { renderOverview } from "./pages/overview";
import { renderSignals } from "./pages/signals";
import {
    content,
    descriptions,
    requireElement,
    state,
} from "./state";
import {
    applyTheme,
    currentTheme,
    initTheme,
    onThemeChange,
} from "./theme";
import type { Theme } from "./theme";
import type { PageName } from "./types";

const PAGES: Record<
    PageName,
    () => Promise<void>
> = {
    overview: renderOverview,
    inventory: renderInventory,
    funnel: renderFunnel,
    signals: renderSignals,
    forecast: renderForecast,
    analyst: renderAnalyst,
    data: renderData,
};

/**
 * Guards the `data-page` attribute coming out of the
 * markup, so a typo in index.html surfaces as a visible
 * error instead of a blank page.
 */
function isPageName(
    value: string | undefined,
): value is PageName {
    return (
        value !== undefined && value in PAGES
    );
}

function setLoading(): void {
    disposeCharts();

    content.innerHTML = `
        <div class="loading">
            Loading...
        </div>
    `;
}

function showError(error: unknown): void {
    disposeCharts();

    const message =
        error instanceof Error
            ? error.message
            : String(error);

    content.innerHTML = `
        <div class="error">
            ${escapeHtml(message)}
        </div>
    `;
}

async function loadPage(): Promise<void> {
    setLoading();

    try {
        await PAGES[state.page]();
    } catch (error) {
        showError(error);
    }
}

function setPage(page: PageName): void {
    state.page = page;

    document
        .querySelectorAll<HTMLButtonElement>(
            ".nav-button",
        )
        .forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset["page"] === page,
            );
        });

    const title =
        page.charAt(0).toUpperCase() +
        page.slice(1);

    requireElement("page-title").textContent =
        title;

    requireElement(
        "page-description",
    ).textContent = descriptions[page];

    renderControls(loadPage);

    void loadPage();
}

async function renderHeroMetadata(): Promise<void> {
    try {
        const data = await fetchDataHealth();

        requireElement(
            "hero-chips",
        ).innerHTML = `

            <span class="chip">
                Read-only
            </span>

            <span class="chip">
                Orders:
                ${escapeHtml(
                    data.order_start || "N/A",
                )}
                →
                ${escapeHtml(
                    data.order_end || "N/A",
                )}
            </span>

            <span class="chip">
                Orders stored:
                ${formatInt(
                    data.counts["orders"],
                )}
            </span>

        `;
    } catch {
        // Header metadata is optional.
    }
}

/**
 * The theme switch.
 *
 * Charts paint with resolved colour values rather than
 * `var(...)`, so a theme change has to redraw them - the CSS
 * alone cannot recolour an SVG stroke that was already set.
 */
function setupTheme(): void {
    const switcher = requireElement("theme-switch");

    const buttons =
        switcher.querySelectorAll<HTMLButtonElement>(
            ".theme-option",
        );

    const paint = (): void => {
        const active = currentTheme();

        buttons.forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                String(
                    button.dataset["theme"] === active,
                ),
            );
        });
    };

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const theme = button.dataset["theme"];

            if (
                theme === "light" ||
                theme === "dark" ||
                theme === "system"
            ) {
                applyTheme(theme satisfies Theme);
            }
        });
    });

    onThemeChange(() => {
        paint();
        redrawCharts();
    });

    initTheme();

    paint();
}

setupTheme();

document
    .querySelectorAll<HTMLButtonElement>(
        ".nav-button",
    )
    .forEach((button) => {
        button.addEventListener("click", () => {
            const page = button.dataset["page"];

            if (isPageName(page)) {
                setPage(page);
            }
        });
    });

requireElement("refresh").addEventListener(
    "click",
    () => {
        void (async () => {
            await renderHeroMetadata();
            await loadPage();
        })();
    },
);

renderControls(loadPage);

void renderHeroMetadata();

void loadPage();
