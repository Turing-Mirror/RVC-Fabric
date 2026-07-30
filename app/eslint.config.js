import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

/**
 * Deliberately narrow: the Rules of Hooks and nothing else.
 *
 * A hook declared after an early `return` shipped a blank window to every user
 * whose install hit that branch — the component threw, React unmounted the
 * whole tree, and there was no visible symptom beyond "白屏". That class of bug
 * is invisible in review and invisible in TypeScript, so it gets a machine
 * check wired into `npm run build`.
 *
 * Style rules are left out on purpose: a lint gate that fails the release build
 * for a formatting opinion would get switched off, and then this check goes
 * with it.
 */
export default [
  { ignores: ["frontend/**", "src-tauri/**", "node_modules/**"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
