# Recipes

Task-oriented guides. Each one uses only real manifest fields and real
command signatures — if a recipe drifts from the code, that is a bug:
[open an issue](https://github.com/aparragithub/odoo-forge/issues).

| Recipe | When you need it |
| --- | --- |
| [Add an addon layer](add-an-addon-layer.md) | Your project needs modules from OCA or any Git repo |
| [Resolve duplicate modules with mount priority](mount-priority.md) | Two addon roots contain the same Odoo module |
| [Override a repo with your fork](fork-override-and-hack.md) | A third-party module needs your patch, or you want to hack on it locally |
| [Enterprise credentials](enterprise-credentials.md) | Your project uses Odoo Enterprise and CI/machines need to clone it |

For the end-to-end flow (validate → lock → project → run), see the
[README quickstart](../../README.md#quickstart) and the
[example runtime guide](../22-example-runtime-guide.md).
