export default {
    async fetch(request, env) {
        // If the request is for an asset, return it
        try {
            return await env.ASSETS.fetch(request);
        } catch (e) {
            return new Response("Not Found", { status: 404 });
        }
    },
};
