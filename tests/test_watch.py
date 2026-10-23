import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import watch_openrazer as w  # noqa: E402


def commit(sha, msg):
    return {"sha": sha, "html_url": f"https://x/{sha}", "commit": {"message": msg}}


class WatchTest(unittest.TestCase):
    def test_matching(self):
        commits = [commit("a1", "Add Basilisk V3 Pro 35K"), commit("b2", "Fix typo"), commit("c3", "Refactor")]
        files = {"a1": [], "b2": [{"filename": "README.md", "patch": "+ nothing"}],
                 "c3": [{"filename": "driver/razerkbd_driver.c", "patch": "+ case USB_DEVICE_ID_RAZER_DEATHSTALKER_V2_PRO_WIRELESS:"}]}
        found = w.matching_commits(commits, lambda sha: {"files": files[sha]})
        self.assertEqual([f["sha"] for f in found], ["a1", "c3"])
        self.assertEqual(found[1]["devices"], ["deathstalker v2 pro"])
        self.assertIn("<!-- a1 c3 -->", w.issue_body(found))


if __name__ == "__main__":
    unittest.main()
