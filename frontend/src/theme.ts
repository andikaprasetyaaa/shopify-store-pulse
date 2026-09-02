/**
 * Light / dark / system theme.
 *
 * Three states rather than two: "system" is the default, so a
 * reader who has never touched the switch follows their OS and
 * is not silently pinned to whichever mode we happened to
 * prefer. Only an explicit choice writes to localStorage.
 *
 * The charts read their colors from CSS custom properties at
 * draw time, so anything that changes the theme has to tell
 * them to redraw - that is what the listener list is for.
 */

const STORAGE_KEY = "store-pulse-theme";

export type Theme = "light" | "dark" | "system";

const THEMES: readonly Theme[] = [
    "light",
    "dark",
    "system",
];

const listeners = new Set<() => void>();

function isTheme(value: string | null): value is Theme {
    return (
        value !== null &&
        (THEMES as readonly string[]).includes(value)
    );
}

/**
 * Storage can throw outright in a private window or with site
 * data blocked, so every access is guarded and simply falls
 * back to following the OS.
 */
export function currentTheme(): Theme {
    try {
        const stored =
            localStorage.getItem(STORAGE_KEY);

        return isTheme(stored) ? stored : "system";
    } catch {
        return "system";
    }
}

export function applyTheme(theme: Theme): void {
    const root = document.documentElement;

    if (theme === "system") {
        root.removeAttribute("data-theme");
    } else {
        root.setAttribute("data-theme", theme);
    }

    try {
        if (theme === "system") {
            localStorage.removeItem(STORAGE_KEY);
        } else {
            localStorage.setItem(
                STORAGE_KEY,
                theme,
            );
        }
    } catch {
        // A theme that cannot be remembered still applies
        // for this visit.
    }

    for (const listener of listeners) {
        listener();
    }
}

export function onThemeChange(
    listener: () => void,
): void {
    listeners.add(listener);
}

/**
 * Reads a design token off the root element.
 *
 * Charts paint with real color values rather than `var(...)`,
 * because an SVG attribute like `stroke` takes a color, and
 * because the drawing code needs the resolved value to build
 * washes and rings.
 */
export function token(name: string): string {
    return getComputedStyle(document.documentElement)
        .getPropertyValue(name)
        .trim();
}

export function initTheme(): void {
    applyTheme(currentTheme());

    // With no explicit choice stored, follow the OS live.
    window
        .matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", () => {
            if (currentTheme() === "system") {
                for (const listener of listeners) {
                    listener();
                }
            }
        });
}
