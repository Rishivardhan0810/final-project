// PART OF: Frontend -- App Entry Point (mounts the React app into the page; you won't need to edit this file)
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
