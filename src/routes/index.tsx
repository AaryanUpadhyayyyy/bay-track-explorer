import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  loader: () => {
    throw redirect({ href: "/hurricanemap/index.html" });
  },
  component: () => null,
});
