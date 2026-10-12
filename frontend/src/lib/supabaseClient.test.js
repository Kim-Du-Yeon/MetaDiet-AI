import { createClient } from "@supabase/supabase-js";

jest.mock("@supabase/supabase-js", () => ({ createClient: jest.fn(() => ({ auth: {} })) }));

test("stores authentication only for the current browser session", () => {
  jest.isolateModules(() => {
    require("./supabaseClient");
  });

  expect(createClient).toHaveBeenCalledWith(
    process.env.REACT_APP_SUPABASE_URL,
    process.env.REACT_APP_SUPABASE_ANON_KEY,
    expect.objectContaining({
      auth: expect.objectContaining({ storage: window.sessionStorage }),
    }),
  );
});
