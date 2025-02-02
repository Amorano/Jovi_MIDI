/**
 * File: util_field.js
 * Project: Jovi_MIDI
 */

function button_action(widget) {
    if (
        widget.options?.reset == undefined &&
        widget.options?.disable == undefined
    ) {
        return 'None'
    }

    if (
        widget.options.reset != undefined &&
        widget.value != widget.options.reset
    ) {
        return 'Reset'
    }

    if (
        widget.options.disable != undefined &&
        widget.value != widget.options.disable
    ) {
        return 'Disable'
    }

    if (widget.options.reset != undefined) {
        return 'No Reset'
    }
    return 'No Disable'
}

function inner_value_change(widget, value, node, pos) {
    widget.value = value
    if (widget.options?.property && widget.options.property in node.properties) {
        node.setProperty(widget.options.property, value)
    }
    if (widget.callback) {
        widget.callback(widget.value, app.canvas, node, event)
    }
}

function drawAnnotated(ctx, node, widget_width, y, H) {
    const litegraph_base = LiteGraph
    const show_text = app.canvas.ds.scale > 0.5
    const margin = 15
    ctx.textAlign = 'left'
    ctx.strokeStyle = litegraph_base.WIDGET_OUTLINE_COLOR
    ctx.fillStyle = litegraph_base.WIDGET_BGCOLOR
    ctx.beginPath()

    if (show_text)
        ctx.roundRect(margin, y, widget_width - margin * 2, H, [H * 0.5])

    else ctx.rect(margin, y, widget_width - margin * 2, H)
    ctx.fill()

    if (show_text) {
        const monospace_font = ctx.font.split(' ')[0] + ' monospace'
        if (!this.disabled) ctx.stroke()

        const button = button_action(this)

        if (button != 'None') {
            ctx.save()
            ctx.font = monospace_font
            if (button.startsWith('No ')) {
                ctx.fillStyle = litegraph_base.WIDGET_OUTLINE_COLOR
            } else {
                ctx.fillStyle = litegraph_base.WIDGET_TEXT_COLOR
            }

            if (button.endsWith('Reset')) {
                ctx.fillText('\u21ba', widget_width - margin - 33, y + H * 0.7)
            } else {
                ctx.fillText('\u2298', widget_width - margin - 33, y + H * 0.7)
            }
            ctx.restore()
        }
        ctx.fillStyle = litegraph_base.WIDGET_TEXT_COLOR
        if (!this.disabled) {
            ctx.beginPath()
            ctx.moveTo(margin + 16, y + 5)
            ctx.lineTo(margin + 6, y + H * 0.5)
            ctx.lineTo(margin + 16, y + H - 5)
            ctx.fill()
            ctx.beginPath()
            ctx.moveTo(widget_width - margin - 16, y + 5)
            ctx.lineTo(widget_width - margin - 6, y + H * 0.5)
            ctx.lineTo(widget_width - margin - 16, y + H - 5)
            ctx.fill()
        }

        ctx.fillStyle = litegraph_base.WIDGET_SECONDARY_TEXT_COLOR
        ctx.fillText(this.label || this.name, margin * 2 + 5, y + H * 0.7)
        ctx.fillStyle = litegraph_base.WIDGET_TEXT_COLOR
        ctx.textAlign = 'right'
        const text = Number(this.value).toFixed(
            this.options.precision !== undefined ? this.options.precision : 3
        )
        let value_offset = margin * 2 + 20

        if (this.options.unit) {
            ctx.save()
            ctx.font = monospace_font
            ctx.fillStyle = litegraph_base.WIDGET_OUTLINE_COLOR
            ctx.fillText(this.options.unit, widget_width - value_offset, y + H * 0.7)
            value_offset += ctx.measureText(this.options.unit).width
            ctx.restore()
        }
        ctx.fillText(text, widget_width - value_offset, y + H * 0.7)

        const value_width = ctx.measureText(text).width
        const name_width = ctx.measureText(this.label || this.name).width
        const free_width =
        widget_width - (value_width + name_width + value_offset + 40)

        let annotation = ''
        if (this.annotation) {
            annotation = this.annotation(this.value, free_width)
        } else if (
            this.options.annotation &&
            this.value in this.options.annotation
        ) {
            annotation = this.options.annotation[this.value]
        }

        if (annotation) {
            ctx.fillStyle = litegraph_base.WIDGET_OUTLINE_COLOR
            const annotation_width = ctx.measureText(annotation).width
            if (free_width < annotation_width) {
                //Enforcing a widget's requested minimum width seems ill supported
                //hiding annotation is best, but existence should still be indicated
                annotation = '…'
            }
            ctx.fillText(
                annotation,
                widget_width - 5 - value_width - value_offset,
                y + H * 0.7
            )
        }
    }
}

function mouseAnnotated(event, [x, y], node) {
    const button = button_action(this)
    const widget_width = this.width || node.size[0]
    const old_value = this.value
    const delta = x < 40 ? -1 : x > widget_width - 48 ? 1 : 0
    const margin = 15
    var allow_scroll = true

    if (delta) {
        if (x > -3 && x < widget_width + 3) {
            allow_scroll = false
        }
    }

    if (allow_scroll && event.type == 'pointermove') {
        if (event.deltaX)
            this.value += event.deltaX * 0.1 * (this.options.step || 1)

        if (this.options.min != null && this.value < this.options.min) {
            this.value = this.options.min
        }

        if (this.options.max != null && this.value > this.options.max) {
            this.value = this.options.max
        }
    } else if (event.type == 'pointerdown') {
        if (x > widget_width - margin - 34 && x < widget_width - margin - 18) {
            if (button == 'Reset') {
                this.value = this.options.reset
            } else if (button == 'Disable') {
                this.value = this.options.disable
            }
        } else {
            this.value += delta * 0.1 * (this.options.step || 1)
            if (this.options.min != null && this.value < this.options.min) {
                this.value = this.options.min
            }
            if (this.options.max != null && this.value > this.options.max) {
                this.value = this.options.max
            }
      }
    } //end mousedown
    else if (event.type == 'pointerup') {
        if (event.click_time < 200 && delta == 0) {
            app.canvas.prompt(
                'Value',
                this.value,
                function (v) {
                    //NOTE: Original code uses eval here. This will not be reproduced
                    this.value = Number(v)
                    inner_value_change(this, this.value, node, [x, y])
                }.bind(this),
                event
            )
        }
    }

    if (old_value != this.value)
        setTimeout(
            function () {
                inner_value_change(this, this.value, node, [x, y])
            }.bind(this),
            20
        )
    return true
}

function makeAnnotated(widget, inputData) {
    const callback_orig = widget.callback
    Object.assign(widget, {
        type: "BOOLEAN",//Horrific, not namespaced, nonsensical, easier than upstreaming
        draw: drawAnnotated,
        mouse: mouseAnnotated,
        computeSize(width) {
            return [width, 20]
        },
        callback(v) {
            if (v == 0) {
                return
            }

            if (this.options?.mod == undefined) {
                return callback_orig.apply(this, arguments);
            }

            const s = this.options.step / 10
            let sh = this.options.mod
            this.value = Math.round((v - sh) / s) * s + sh
        },
        config: inputData,
        options: Object.assign({},  inputData[1], widget.options)
    })
    return widget
}