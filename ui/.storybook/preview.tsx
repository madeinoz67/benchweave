import type { Preview } from "@storybook/react-vite";

import "../src/styles/tokens.css";
import "../src/styles/themes.css";
import "../src/styles/globals.css";

const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Theme",
      toolbar: {
        icon: "paintbrush",
        items: ["light", "dark"],
      },
    },
  },
  initialGlobals: { theme: "light" },
  decorators: [
    (Story, context) => (
      <div className="bw-story-canvas" data-theme={context.globals.theme}>
        <Story />
      </div>
    ),
  ],
  parameters: {
    a11y: { test: "error" },
  },
};

export default preview;
