import overview from "./md/index.md?raw";
import quickstart from "./md/quickstart.md?raw";
import capabilities from "./md/capabilities.md?raw";
import comparison from "./md/comparison.md?raw";
import sources from "./md/sources.md?raw";
import pipeline from "./md/pipeline.md?raw";
import contextControl from "./md/context-control.md?raw";
import notesMindmaps from "./md/notes-mindmaps.md?raw";
import studio from "./md/studio.md?raw";
import modelHub from "./md/model-hub.md?raw";
import configuration from "./md/configuration.md?raw";
import deployment from "./md/deployment.md?raw";
import security from "./md/security.md?raw";
import performance from "./md/performance.md?raw";
import api from "./md/api.md?raw";
import architecture from "./md/architecture.md?raw";
import evaluation from "./md/evaluation.md?raw";
import troubleshooting from "./md/troubleshooting.md?raw";
import faq from "./md/faq.md?raw";

export const docs = {
  index: { title: "Overview", group: "Start here", body: overview },
  quickstart: { title: "Quickstart", group: "Start here", body: quickstart },
  capabilities: {
    title: "Capabilities",
    group: "Start here",
    body: capabilities,
  },
  comparison: {
    title: "How it compares",
    group: "Start here",
    body: comparison,
  },
  sources: { title: "Sources", group: "Using the workspace", body: sources },
  pipeline: {
    title: "Retrieval pipeline",
    group: "Using the workspace",
    body: pipeline,
  },
  "context-control": {
    title: "Context control",
    group: "Using the workspace",
    body: contextControl,
  },
  "notes-mindmaps": {
    title: "Notes & mind maps",
    group: "Using the workspace",
    body: notesMindmaps,
  },
  studio: {
    title: "Repository Studio",
    group: "Using the workspace",
    body: studio,
  },
  "model-hub": {
    title: "Model Hub",
    group: "Using the workspace",
    body: modelHub,
  },
  configuration: {
    title: "Configuration",
    group: "Deploy & configure",
    body: configuration,
  },
  deployment: {
    title: "Deployment",
    group: "Deploy & configure",
    body: deployment,
  },
  security: {
    title: "Security & privacy",
    group: "Deploy & configure",
    body: security,
  },
  performance: {
    title: "Performance",
    group: "Deploy & configure",
    body: performance,
  },
  api: { title: "API reference", group: "Reference", body: api },
  architecture: { title: "Architecture", group: "Reference", body: architecture },
  evaluation: { title: "Evaluation", group: "Reference", body: evaluation },
  troubleshooting: {
    title: "Troubleshooting",
    group: "Reference",
    body: troubleshooting,
  },
  faq: { title: "FAQ", group: "Reference", body: faq },
};

export const docList = Object.entries(docs).map(([slug, doc]) => ({
  slug,
  ...doc,
}));
