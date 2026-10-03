import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

export default [
  ...nextCoreWebVitals,
  {
    // The react-hooks v7 `set-state-in-effect` rule is stricter than this app
    // needs: we intentionally set state inside effects to read URL query
    // params and to reset dialog/form state when a dialog opens.
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    ignores: ["eslint.config.mjs"],
  },
];
