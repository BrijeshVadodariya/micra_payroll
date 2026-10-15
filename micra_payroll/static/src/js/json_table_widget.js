import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, useState } from "@odoo/owl";
import { View } from "@web/views/view";
import { useService } from "@web/core/utils/hooks";

export class JsonTableWidget extends Component {
    static components = { View };
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            modelName: null,
            context: {},
            display: { controlPanel: false },
        });

        onWillStart(async () => {
            const dataStr = this.props.record.data[this.props.name] || "{}";
            const modelName = this.props.record.data.model_name;
            
            if (modelName) {
                this.state.modelName = modelName;
                try {
                    // Call the backend to deeply clean and format the JSON data into a safe Odoo 'default_' context
                    const ctx = await this.orm.call("recycle.bin", "get_clean_preview_context", [modelName, dataStr]);
                    ctx['recycle_bin_preview'] = true;
                    this.state.context = ctx;
                } catch (e) {
                    console.warn("Could not generate clean preview context", e);
                }
            }
        });
    }
}

JsonTableWidget.template = "micra_payroll.JsonTableWidget";
JsonTableWidget.props = {
    ...standardFieldProps,
};

registry.category("fields").add("json_table", {
    component: JsonTableWidget,
});
