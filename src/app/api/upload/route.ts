import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";
import { NextResponse } from "next/server";

// Client-upload token endpoint (design §1-①): the browser uploads the PDF
// directly to Vercel Blob, bypassing the 4.5MB serverless body limit.
// After upload the CLIENT calls POST /api/parse (Python) — not the
// onUploadCompleted callback, which cannot reach localhost in dev.
export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as HandleUploadBody;
  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async () => ({
        allowedContentTypes: ["application/pdf"],
        maximumSizeInBytes: 200 * 1024 * 1024, // design §6 upload cap
        addRandomSuffix: true,
      }),
      onUploadCompleted: async () => {
        /* parse is triggered by the client — see src/app/page.tsx */
      },
    });
    return NextResponse.json(jsonResponse);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
