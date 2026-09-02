import { defineConfig } from "vite";

// The FastAPI app serves the built files: `/` returns
// dist/index.html and `/assets` is mounted from
// dist/assets. Keeping the default base of "/" is
// therefore correct, and the dev server proxies /api
// to the running uvicorn process so `npm run dev`
// talks to the same DuckDB data as production.
export default defineConfig({
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
            },
        },
    },

    build: {
        outDir: "dist",
        emptyOutDir: true,
        sourcemap: true,
    },
});
