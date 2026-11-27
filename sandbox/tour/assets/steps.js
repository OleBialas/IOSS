// The steps of the repository tour. Edit the text here.
//
// element: a CSS selector. {repo} becomes the repository path, for example
//          /tinystats/tinystats. A step without element shows in the centre.
//          The tour skips a step when the page has no matching element.
// title, description: the text of the step. The description can contain HTML.

window.IOSS_TOUR_STEPS = [
  {
    title: "Welcome to tinystats",
    description:
      "This tour shows the files that each open source project has. It takes 1 minute.",
  },
  {
    element: '#repo-files-table a[title="README.md"]',
    title: "README.md",
    description:
      "Read this file first. It tells what the project does, how to install it and how to use it. Forgejo shows it below the file list.",
  },
  {
    element: '#repo-files-table a[title="CONTRIBUTING.md"]',
    title: "CONTRIBUTING.md",
    description:
      "The rules for contributors: how to set up the environment, how to name a branch, how to test and how to open a pull request. <b>Read it before your first change.</b>",
  },
  {
    element: '#repo-files-table a[title="tests"]',
    title: "tests/",
    description:
      "The tests. Each change in behaviour needs a test here. Run them with <code>uv run pytest</code>.",
  },
  {
    element: 'a.item[href="{repo}/issues"]',
    title: "Issues",
    description:
      "Bugs and ideas. Find an issue with the label <code>good first issue</code> for your first contribution.",
  },
  {
    title: "End of the tour",
    description:
      "You know the parts of the project now. Start the tour again with the <b>Start tour</b> button.",
  },
];
