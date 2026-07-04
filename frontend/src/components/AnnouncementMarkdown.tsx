import { Box } from "@mui/material";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";


const components: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
};


export function AnnouncementMarkdown({ children }: { children: string }) {
  return (
    <Box
      className="announcement-markdown"
      sx={{
        color: "text.primary",
        overflowWrap: "anywhere",
        "& > :first-of-type": { mt: 0 },
        "& > :last-child": { mb: 0 },
        "& h1, & h2, & h3, & h4": { mt: 2.25, mb: 1, lineHeight: 1.35, letterSpacing: 0 },
        "& h1": { fontSize: "1.3rem" },
        "& h2": { fontSize: "1.15rem" },
        "& h3, & h4": { fontSize: "1rem" },
        "& p": { my: 1, lineHeight: 1.75 },
        "& ul, & ol": { my: 1, pl: 3 },
        "& li": { my: 0.5, lineHeight: 1.7 },
        "& li > p": { my: 0.25 },
        "& a": { color: "primary.main", fontWeight: 650, textUnderlineOffset: "3px" },
        "& blockquote": {
          m: "12px 0",
          px: 2,
          py: 0.5,
          borderLeft: 3,
          borderColor: "primary.main",
          bgcolor: "action.hover",
          color: "text.secondary",
        },
        "& code": {
          px: 0.75,
          py: 0.25,
          borderRadius: 0.5,
          bgcolor: "action.hover",
          fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
          fontSize: "0.88em",
        },
        "& pre": {
          my: 1.5,
          p: 1.5,
          maxWidth: "100%",
          overflowX: "auto",
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "background.default",
        },
        "& pre code": { p: 0, bgcolor: "transparent" },
        "& table": {
          display: "block",
          width: "max-content",
          maxWidth: "100%",
          my: 1.5,
          overflowX: "auto",
          borderCollapse: "collapse",
        },
        "& th, & td": { px: 1.25, py: 0.75, border: 1, borderColor: "divider", textAlign: "left" },
        "& th": { bgcolor: "action.hover", fontWeight: 750 },
        "& hr": { my: 2, border: 0, borderTop: 1, borderColor: "divider" },
        "& img": { display: "block", maxWidth: "100%", height: "auto", my: 1.5, borderRadius: 1 },
        "& input[type='checkbox']": { mr: 0.75, accentColor: "primary.main" },
      }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{children}</ReactMarkdown>
    </Box>
  );
}
