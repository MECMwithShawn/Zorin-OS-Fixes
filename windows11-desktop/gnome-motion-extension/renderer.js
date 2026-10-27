import Cairo from 'cairo';
import {layers, normalize} from './model.js';

export function paint(cr, width, height, config, seconds, focus = null, clear = true) {
    if (clear) {
        cr.save(); cr.setOperator(Cairo.Operator.CLEAR); cr.paint(); cr.restore();
    }
    const c = normalize(config), rgb = [1, 3, 5].map(i => parseInt(c.accent.slice(i, i + 2), 16) / 255);
    for (const layer of layers(c, width, height, seconds, focus)) {
        const color = layer.tone ? [rgb[2] * .7, rgb[0] * .8, rgb[1]] : rgb;
        cr.save();
        if (layer.edge) {cr.rectangle(0, 0, width, 2); cr.clip();}
        cr.translate(layer.x, layer.y); cr.scale(layer.rx, layer.ry);
        const gradient = new Cairo.RadialGradient(0, 0, 0, 0, 0, 1);
        gradient.addColorStopRGBA(0, ...color, layer.alpha);
        gradient.addColorStopRGBA(.45, ...color, layer.alpha * .45);
        gradient.addColorStopRGBA(1, ...color, 0);
        cr.setSource(gradient); cr.arc(0, 0, 1, 0, Math.PI * 2); cr.fill(); cr.restore();
    }
}
