/**
 * File: node_midi_reader.js
 * Project: Jovi_MIDI
 */

import { app } from "../../scripts/app.js";

const _id = "MIDI READER (JOV_MIDI)";

app.registerExtension({
    name: 'jovi_midi.node.' + _id,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== _id) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = async function () {
            const me = onNodeCreated?.apply(this);

            return me;
        }
    }
});
