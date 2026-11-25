import { getToken } from "@/lib/api";
import { startReplay } from "@/lib/replay";

startReplay(Boolean(getToken()));
