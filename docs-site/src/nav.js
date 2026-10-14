export const nav = [
  {
    title: "Start here",
    items: [
      { title: "Overview", slug: "index" },
      { title: "Quickstart", slug: "quickstart" },
      { title: "Capabilities", slug: "capabilities" },
      { title: "How it compares", slug: "comparison" },
    ],
  },
  {
    title: "Using the workspace",
    items: [
      { title: "Sources", slug: "sources" },
      { title: "Retrieval pipeline", slug: "pipeline" },
      { title: "Context control", slug: "context-control" },
      { title: "Notes & mind maps", slug: "notes-mindmaps" },
      { title: "Repository Studio", slug: "studio" },
      { title: "Model Hub", slug: "model-hub" },
    ],
  },
  {
    title: "Deploy & configure",
    items: [
      { title: "Configuration", slug: "configuration" },
      { title: "Deployment", slug: "deployment" },
      { title: "Security & privacy", slug: "security" },
      { title: "Performance", slug: "performance" },
    ],
  },
  {
    title: "Reference",
    items: [
      { title: "API reference", slug: "api" },
      { title: "Architecture", slug: "architecture" },
      { title: "Evaluation", slug: "evaluation" },
      { title: "Troubleshooting", slug: "troubleshooting" },
      { title: "FAQ", slug: "faq" },
    ],
  },
];

export const flatNav = nav.flatMap((group) =>
  group.items.map((item) => ({ ...item, group: group.title })),
);
